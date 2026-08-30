"""
Two-stage unlevered free-cash-flow DCF, built around one explicit
Assumptions object rather than hidden internal ratios.

Every number that goes into the projection (growth rate, EBIT margin, tax
rate, D&A %, CapEx %, working-capital-change %, terminal growth, WACC
build-up) is a named field with a computed default and an optional
override. This is the DCF equivalent of an Excel "Assumptions" tab:
nothing is buried inside a formula that only the model author can see.

Core valuation logic:
- Project unlevered free cash flow to the firm:
      FCFF = EBIT * (1 - tax) + D&A - CapEx - ΔNWC
- Discount FCFF using WACC, not cost of equity.
- Convert enterprise value to equity value by subtracting debt and adding
  cash before dividing by shares.

Simplifications made deliberately for v1 (documented here, not hidden):
- Capital structure is assumed constant during the forecast period.
- Debt is proxied with book debt because free market-value debt data is not
  consistently available.
- Cost of debt is estimated from reported interest expense and debt where
  possible, with a risk-free-rate-plus-spread fallback.
- Each operating ratio is held flat across the forecast period at its
  default or overridden value.
- Equity risk premium is a fixed market-wide constant.
"""

from dataclasses import dataclass, replace
from statistics import median
from typing import Optional

from app.pipeline.yahoo import FinancialSnapshot

EQUITY_RISK_PREMIUM = 0.05
DEFAULT_TERMINAL_GROWTH = 0.025
FORECAST_YEARS = 5
DEFAULT_DEBT_SPREAD = 0.015
MIN_DEBT_SPREAD = 0.005


@dataclass
class Assumptions:
    growth_rate: float
    discount_rate: float          # final WACC used by the DCF
    ebit_margin: float
    tax_rate: float
    da_pct: float
    capex_pct: float
    nwc_pct: float
    interest_pct: float
    terminal_growth: float
    risk_free_rate: float
    beta: float
    equity_risk_premium: float
    cost_of_debt: float           # pre-tax cost of debt
    debt_weight: float            # D / (D + E), using book debt + market equity proxy
    cost_of_equity: float         # CAPM result, shown for transparency


def _avg_ratio(numerator_history: list, denominator_history: list) -> float:
    """Median (not mean) of the year-by-year ratio.

    Free financial-statement data occasionally has one badly mismatched
    year. A median is much less sensitive to one outlier than a mean.
    """
    pairs = list(zip(numerator_history, denominator_history))
    if not pairs:
        return 0.0
    ratios = [n / d for n, d in pairs if d]
    return median(ratios) if ratios else 0.0


def _cagr(history: list) -> float:
    if len(history) < 2 or history[0] <= 0:
        return 0.0
    n = len(history) - 1
    return (history[-1] / history[0]) ** (1 / n) - 1


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(min(value, upper), lower)


def _latest_positive(history: list) -> float:
    for value in reversed(history or []):
        if value and value > 0:
            return float(value)
    return 0.0


def _default_growth_rate(snap: FinancialSnapshot) -> float:
    g = _cagr(snap.revenue_history)
    return _clamp(g, -0.10, 0.30)


def _default_tax_rate(snap: FinancialSnapshot) -> float:
    rate = _avg_ratio(snap.tax_paid_history, snap.pretax_income_history)
    return _clamp(rate, 0.10, 0.35) if rate else 0.21


def _default_ebit_margin(snap: FinancialSnapshot) -> float:
    margin = _avg_ratio(snap.ebit_history, snap.revenue_history)
    return _clamp(margin, -0.20, 0.45)


def _cost_of_equity(risk_free_rate: float, beta: float, equity_risk_premium: float) -> float:
    return risk_free_rate + beta * equity_risk_premium


def _default_debt_weight(snap: FinancialSnapshot) -> float:
    """Default capital-structure weight for WACC.

    True WACC should use market values for both debt and equity. Free APIs
    usually do not provide a reliable market value of debt, so this uses:
        D = latest reported total debt
        E = current market price * shares outstanding

    Cash is not netted here because the DCF later bridges enterprise value
    to equity value by subtracting debt and adding cash. Netting cash in
    both places would double-count it.
    """
    debt = max(float(snap.total_debt or 0.0), 0.0)
    market_equity = max(float(snap.current_price or 0.0) * float(snap.shares_outstanding or 0.0), 0.0)
    capital = debt + market_equity
    if capital <= 0:
        return 0.0
    return _clamp(debt / capital, 0.0, 0.95)


def _default_cost_of_debt(snap: FinancialSnapshot, risk_free_rate: float) -> float:
    """Estimate pre-tax cost of debt.

    Preferred estimate: latest reported interest expense divided by average
    debt. Because this is a backward-looking accounting yield, the result is
    not allowed to sit far below today's risk-free rate; the fallback is the
    risk-free rate plus a modest credit spread.
    """
    interest = _latest_positive(snap.interest_expense_history)
    debt_history = getattr(snap, "total_debt_history", None) or []

    avg_debt = 0.0
    if len(debt_history) >= 2 and debt_history[-1] > 0 and debt_history[-2] > 0:
        avg_debt = (float(debt_history[-1]) + float(debt_history[-2])) / 2
    elif snap.total_debt and snap.total_debt > 0:
        avg_debt = float(snap.total_debt)

    historical_yield = interest / avg_debt if interest > 0 and avg_debt > 0 else 0.0
    fallback_yield = risk_free_rate + DEFAULT_DEBT_SPREAD

    if historical_yield > 0:
        cost = max(historical_yield, risk_free_rate + MIN_DEBT_SPREAD)
    else:
        cost = fallback_yield

    return _clamp(cost, 0.005, 0.20)


def _wacc(assumptions: Assumptions) -> float:
    debt_weight = _clamp(assumptions.debt_weight, 0.0, 0.95)
    equity_weight = 1 - debt_weight
    after_tax_cost_of_debt = assumptions.cost_of_debt * (1 - assumptions.tax_rate)
    return equity_weight * assumptions.cost_of_equity + debt_weight * after_tax_cost_of_debt


def _with_recomputed_wacc(assumptions: Assumptions) -> Assumptions:
    cost_of_equity = _cost_of_equity(
        assumptions.risk_free_rate,
        assumptions.beta,
        assumptions.equity_risk_premium,
    )
    interim = replace(assumptions, cost_of_equity=cost_of_equity)
    return replace(interim, discount_rate=_wacc(interim))


def default_assumptions(snap: FinancialSnapshot, risk_free_rate: float) -> Assumptions:
    """Every field computed fresh from the company's own historical data,
    with no overrides applied. This is what the sliders start at."""
    beta = snap.beta if snap.beta else 1.0
    tax_rate = _default_tax_rate(snap)
    cost_of_equity = _cost_of_equity(risk_free_rate, beta, EQUITY_RISK_PREMIUM)
    base = Assumptions(
        growth_rate=_default_growth_rate(snap),
        discount_rate=0.0,  # filled by _with_recomputed_wacc below
        ebit_margin=_default_ebit_margin(snap),
        tax_rate=tax_rate,
        da_pct=_avg_ratio(snap.da_history, snap.revenue_history),
        capex_pct=abs(_avg_ratio(snap.capex_history, snap.revenue_history)),
        nwc_pct=_avg_ratio(snap.nwc_change_history, snap.revenue_history),
        interest_pct=_avg_ratio(snap.interest_expense_history, snap.revenue_history),
        terminal_growth=DEFAULT_TERMINAL_GROWTH,
        risk_free_rate=risk_free_rate,
        beta=beta,
        equity_risk_premium=EQUITY_RISK_PREMIUM,
        cost_of_debt=_default_cost_of_debt(snap, risk_free_rate),
        debt_weight=_default_debt_weight(snap),
        cost_of_equity=cost_of_equity,
    )
    return _with_recomputed_wacc(base)


def apply_overrides(defaults: Assumptions, overrides: dict) -> Assumptions:
    """Apply only fields actually present in `overrides`.

    The model now discounts FCFF at WACC. Therefore risk-free rate, beta,
    ERP, cost of debt, debt weight, and tax rate all feed into the discount
    rate. If the caller changes any of them and does not directly override
    discount_rate, WACC is recomputed automatically. A direct discount_rate
    override still wins last because advanced users may want to force a
    manual WACC.
    """
    resolved = defaults

    fields = [
        "growth_rate", "ebit_margin", "tax_rate", "da_pct", "capex_pct", "nwc_pct",
        "terminal_growth", "risk_free_rate", "beta", "equity_risk_premium",
        "cost_of_debt", "debt_weight",
    ]
    changes = {field: overrides[field] for field in fields if overrides.get(field) is not None}
    if changes:
        resolved = replace(resolved, **changes)
        if any(field in changes for field in [
            "risk_free_rate", "beta", "equity_risk_premium", "cost_of_debt", "debt_weight", "tax_rate",
        ]):
            resolved = _with_recomputed_wacc(resolved)

    if overrides.get("discount_rate") is not None:
        resolved = replace(resolved, discount_rate=overrides["discount_rate"])

    return resolved


def project_free_cash_flow_to_firm(
    snap: FinancialSnapshot,
    assumptions: Assumptions,
    forecast_years: int = FORECAST_YEARS,
) -> list:
    """Project unlevered FCF.

        FCFF = EBIT * (1 - tax) + D&A - CapEx - ΔNWC

    Interest expense is deliberately excluded because debt is handled by
    WACC and by the enterprise-value-to-equity-value bridge.
    """
    revenue = snap.revenue_history[-1]
    projections = []
    for _ in range(forecast_years):
        revenue = revenue * (1 + assumptions.growth_rate)
        ebit = revenue * assumptions.ebit_margin
        nopat = ebit * (1 - assumptions.tax_rate)
        da = revenue * assumptions.da_pct
        capex = revenue * assumptions.capex_pct
        delta_nwc = revenue * assumptions.nwc_pct
        fcff = nopat + da - capex - delta_nwc
        projections.append(fcff)
    return projections


def project_free_cash_flow_to_equity(
    snap: FinancialSnapshot,
    assumptions: Assumptions,
    forecast_years: int = FORECAST_YEARS,
) -> list:
    """Backward-compatible wrapper used by older frontend response keys.

    The values returned are now unlevered FCF/FCFF, not levered FCFE.
    """
    return project_free_cash_flow_to_firm(snap, assumptions, forecast_years)


def discount_cash_flows(cash_flows: list, discount_rate: float, terminal_growth: float):
    discounted = [cf / (1 + discount_rate) ** t for t, cf in enumerate(cash_flows, start=1)]

    terminal_value = cash_flows[-1] * (1 + terminal_growth) / (discount_rate - terminal_growth)
    discounted_terminal = terminal_value / (1 + discount_rate) ** len(cash_flows)

    present_value = sum(discounted) + discounted_terminal
    return present_value, discounted, discounted_terminal


@dataclass
class ValuationResult:
    fair_value_per_share: float
    current_price: float
    gap_percent: float
    verdict: str
    projected_fcfe: list
    discounted_fcfe: list
    terminal_value_discounted: float
    years: list
    enterprise_value: float = 0.0
    equity_value: float = 0.0
    terminal_value_share: float = 0.0   # discounted terminal value / enterprise value
    health_flags: list = None           # model fragility warnings


def _dcf_health_flags(projections: list, enterprise_value: float, term_disc: float, assumptions: Assumptions, fair_value: float) -> list:
    """Warn when a DCF number is arithmetically valid but economically fragile."""
    flags = []

    if fair_value < 0:
        flags.append(
            "Projected free cash flow is persistently negative, so the model produces a negative "
            "intrinsic value. A DCF is not meaningful for a business that is not expected to generate "
            "positive cash flow over the forecast period."
        )
    elif projections and projections[-1] < 0:
        flags.append(
            "Free cash flow is negative in the final forecast year, which makes the terminal value "
            "and the overall valuation unreliable. The result is very sensitive to growth and margin assumptions."
        )

    spread = assumptions.discount_rate - assumptions.terminal_growth
    if 0 < spread < 0.02:
        flags.append(
            f"The gap between WACC ({assumptions.discount_rate * 100:.1f}%) and terminal growth "
            f"({assumptions.terminal_growth * 100:.1f}%) is only {spread * 100:.1f} percentage points. "
            "Terminal value becomes extremely sensitive when this spread is this small."
        )

    if enterprise_value > 0:
        tv_share = term_disc / enterprise_value
        if tv_share > 0.90:
            flags.append(
                f"About {tv_share * 100:.0f}% of enterprise value comes from the terminal value, "
                "meaning the explicit 5-year forecast contributes very little to the valuation."
            )

    return flags


def run_valuation(snap: FinancialSnapshot, assumptions: Assumptions) -> ValuationResult:
    if assumptions.discount_rate <= assumptions.terminal_growth:
        raise ValueError("WACC / discount rate must be greater than the terminal growth rate")

    projections = project_free_cash_flow_to_firm(snap, assumptions)
    enterprise_value, discounted, term_disc = discount_cash_flows(
        projections, assumptions.discount_rate, assumptions.terminal_growth
    )

    equity_value = enterprise_value - snap.total_debt + snap.cash_and_equivalents
    fair_value = equity_value / snap.shares_outstanding if snap.shares_outstanding else 0.0
    gap = ((fair_value - snap.current_price) / snap.current_price * 100) if snap.current_price else 0.0

    if gap > 10:
        verdict = "undervalued"
    elif gap < -10:
        verdict = "overvalued"
    else:
        verdict = "fairly valued"

    tv_share = (term_disc / enterprise_value) if enterprise_value else 0.0
    health_flags = _dcf_health_flags(projections, enterprise_value, term_disc, assumptions, fair_value)

    return ValuationResult(
        fair_value_per_share=fair_value,
        current_price=snap.current_price,
        gap_percent=gap,
        verdict=verdict,
        projected_fcfe=projections,
        discounted_fcfe=discounted,
        terminal_value_discounted=term_disc,
        years=list(range(1, len(projections) + 1)),
        enterprise_value=enterprise_value,
        equity_value=equity_value,
        terminal_value_share=tv_share,
        health_flags=health_flags,
    )


def build_sensitivity_grid(snap: FinancialSnapshot, assumptions: Assumptions) -> dict:
    """Varies only growth rate and final WACC/discount rate around the
    current assumptions. The debt/cost-of-debt build-up is held constant
    for the sensitivity table unless the user changes it separately."""
    growth_steps = [assumptions.growth_rate + delta for delta in [-0.04, -0.02, 0.0, 0.02, 0.04]]
    discount_steps = [assumptions.discount_rate + delta for delta in [-0.02, -0.01, 0.0, 0.01, 0.02]]

    grid = []
    for dr in discount_steps:
        row = []
        for gr in growth_steps:
            if dr <= assumptions.terminal_growth:
                row.append(None)
                continue
            try:
                cell_assumptions = replace(assumptions, growth_rate=gr, discount_rate=dr)
                result = run_valuation(snap, cell_assumptions)
                row.append(round(result.fair_value_per_share, 2))
            except Exception:
                row.append(None)
        grid.append(row)

    return {
        "growth_rates": [round(g * 100, 1) for g in growth_steps],
        "discount_rates": [round(d * 100, 1) for d in discount_steps],
        "values": grid,
        "current_cell": {"row": 2, "col": 2},
    }


def solve_implied_growth_rate(snap: FinancialSnapshot, assumptions: Assumptions) -> Optional[float]:
    """Binary search for the revenue growth rate that would make this
    DCF's fair value equal the current market price, holding every other
    assumption fixed.

    This is a reverse-DCF diagnostic. It is not a forecast. If the implied
    growth rate is much higher than the historical/default growth rate, the
    market may be pricing in stronger future growth, higher margins, a lower
    required return, or all three.
    """
    if not snap.current_price:
        return None

    def fair_value_at(growth_rate: float) -> Optional[float]:
        try:
            result = run_valuation(snap, replace(assumptions, growth_rate=growth_rate))
            return result.fair_value_per_share
        except ValueError:
            return None

    lo, hi = -0.5, 2.0
    lo_val, hi_val = fair_value_at(lo), fair_value_at(hi)
    if lo_val is None or hi_val is None or not (lo_val <= snap.current_price <= hi_val):
        return None

    for _ in range(80):
        mid = (lo + hi) / 2
        mid_val = fair_value_at(mid)
        if mid_val is None:
            return None
        if abs(mid_val - snap.current_price) < 0.005:
            return mid
        if mid_val < snap.current_price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def solve_discount_rate_for_target_price(
    snap: FinancialSnapshot,
    assumptions: Assumptions,
    target_price: float,
) -> Optional[float]:
    """Reverse-solve the WACC/discount rate needed to hit any target
    per-share value, holding the cash-flow forecast and EV-to-equity bridge
    fixed.

    This is useful in two places:
    - market-implied WACC, where target_price is the live share price;
    - benchmark-implied WACC, where target_price is a third-party DCF value
      such as FMP's prebuilt DCF.
    """
    if not target_price or target_price <= 0:
        return None

    def fair_value_at(discount_rate: float) -> Optional[float]:
        try:
            result = run_valuation(snap, replace(assumptions, discount_rate=discount_rate))
            return result.fair_value_per_share
        except ValueError:
            return None

    lo = assumptions.terminal_growth + 0.0001
    hi = 0.50
    lo_val, hi_val = fair_value_at(lo), fair_value_at(hi)

    # Fair value falls as WACC rises. If the target is not between the
    # low-WACC and high-WACC valuations, no sensible implied WACC can be shown.
    if lo_val is None or hi_val is None or not (hi_val <= target_price <= lo_val):
        return None

    for _ in range(80):
        mid = (lo + hi) / 2
        mid_val = fair_value_at(mid)
        if mid_val is None:
            return None
        if abs(mid_val - target_price) < 0.005:
            return mid
        if mid_val > target_price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def solve_implied_discount_rate(snap: FinancialSnapshot, assumptions: Assumptions) -> Optional[float]:
    """Reverse-solve the WACC/discount rate that would make this DCF
    equal the current market price, holding growth, margins, tax, CapEx,
    D&A, working capital, debt, cash, and shares fixed.

    This is the most useful sanity check when users say the fair value is
    "wrong". A DCF can be mathematically correct and still sit far away
    from the market price because the default required return is too high
    or the forecast is too conservative. The reverse WACC makes that
    disagreement explicit instead of hiding it behind an over/undervalued
    label.
    """
    if not snap.current_price:
        return None
    return solve_discount_rate_for_target_price(snap, assumptions, snap.current_price)
