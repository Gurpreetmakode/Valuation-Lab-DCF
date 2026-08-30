import os
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.cache import get_json as cache_get_json, make_key as cache_make_key, set_json as cache_set_json, stats as cache_stats
from app.models import dcf
from app.models.backtest import run_backtest
from app.models.peers import fetch_peer_average_pe
from app.models.quality import check_suitability
from app.pipeline.financials import fetch_financial_snapshot_hybrid
from app.pipeline.fmp import (
    cross_check_against_fmp,
    debug_fmp_snapshot_status,
    fetch_fmp_dcf_benchmarks,
    fetch_fmp_price_history,
    is_configured as fmp_is_configured,
)
from app.pipeline.rates import fetch_risk_free_rate_for_currency
from app.pipeline.search import search_tickers
from app.pipeline.yahoo import FinancialSnapshot, fetch_financial_snapshot as fetch_yahoo_financial_snapshot, fetch_price_history

router = APIRouter()


def _fmp_direct_dcf_enabled() -> bool:
    """When enabled, the headline fair value comes from FMP's own DCF endpoint.

    The app still computes its transparent internal DCF so the assumptions,
    projection chart, sensitivity table, and reverse-DCF diagnostics remain
    visible. This mode is for users who want the headline value to match FMP
    rather than the app's own simple 5-year DCF assumptions.
    """
    return os.environ.get("FMP_DIRECT_DCF", "1").strip().lower() not in {"0", "false", "no", "off"}


def _fmp_price_history_enabled() -> bool:
    """Keep price-history charts off FMP by default to protect API quota."""
    return os.environ.get("FMP_PRICE_HISTORY", "0").strip().lower() in {"1", "true", "yes", "on"}


def _verdict_from_gap(gap: float) -> str:
    if gap > 10:
        return "undervalued"
    if gap < -10:
        return "overvalued"
    return "fairly valued"


# Every field a caller may override. Query params use these exact names.
OVERRIDABLE_FIELDS = [
    "growth_rate", "discount_rate", "risk_free_rate", "beta", "equity_risk_premium",
    "cost_of_debt", "debt_weight",
    "ebit_margin", "tax_rate", "da_pct", "capex_pct", "nwc_pct", "terminal_growth",
]


def _snapshot_cache_key(ticker: str, view: str) -> str:
    return cache_make_key("snapshot", view, ticker.upper())


def _backtest_cache_key(ticker: str, view: str) -> str:
    return cache_make_key("backtest", view, ticker.upper())


def _peer_cache_key(sector: str, ticker: str) -> str:
    return cache_make_key("peer", sector or "", ticker.upper())


def _price_history_cache_key(ticker: str, years: int, source_pref: str) -> str:
    return cache_make_key("price-history", ticker.upper(), years, source_pref)


def _snapshot_from_cache(ticker: str, view: str) -> Optional[FinancialSnapshot]:
    cached = cache_get_json(_snapshot_cache_key(ticker, view))
    if not isinstance(cached, dict):
        return None
    try:
        return FinancialSnapshot(**cached)
    except Exception:
        return None


def _save_snapshot_to_cache(ticker: str, view: str, snap: FinancialSnapshot) -> None:
    cache_set_json(_snapshot_cache_key(ticker, view), asdict(snap))


def _fetch_snapshot_uncached(ticker: str, view: str) -> FinancialSnapshot:
    if view == "yfinance":
        # Force the free/raw Yahoo route for the Yahoo DCF tab.
        snap = fetch_yahoo_financial_snapshot(ticker)
        snap.data_source = "Yahoo Finance"
        snap.data_warnings.append(
            "Yahoo DCF tab: financial statements come from Yahoo/yfinance-style data and the valuation is "
            "calculated by this app's transparent FCFF/WACC model. It is not expected to match FMP's "
            "prebuilt DCF endpoint exactly."
        )
        return snap

    # FMP tab should use FMP's direct DCF endpoint for the headline value.
    # Yahoo is used only as a scaffold for metadata and the internal comparison model.
    if fmp_is_configured() and _fmp_direct_dcf_enabled():
        snap = fetch_yahoo_financial_snapshot(ticker)
        snap.data_source = "Yahoo Finance scaffold"
        snap.data_warnings.append(
            "FMP DCF tab: headline fair value comes from FMP's direct DCF endpoint. "
            "Yahoo/yfinance is used only as a scaffold for metadata and the app's optional "
            "internal comparison model, so FMP statement endpoints are not required for this tab."
        )
        return snap

    return fetch_financial_snapshot_hybrid(ticker)


def _fetch_snapshot_cached(ticker: str, view: str) -> FinancialSnapshot:
    cached = _snapshot_from_cache(ticker, view)
    if cached is not None:
        return cached
    snap = _fetch_snapshot_uncached(ticker, view)
    _save_snapshot_to_cache(ticker, view, snap)
    return snap


def _serialise_backtest(backtest) -> dict:
    return {
        "available": backtest.available,
        "reason": backtest.reason,
        "actual_price_now": backtest.actual_price_now,
        "correct_count": backtest.correct_count,
        "total_count": backtest.total_count,
        "checkpoints": [
            {
                "as_of_date": c.as_of_date,
                "implied_fair_value_then": c.implied_fair_value_then,
                "actual_price_then": c.actual_price_then,
                "price_change_pct": c.price_change_pct,
                "model_gap_then_pct": c.model_gap_then_pct,
                "direction_correct": c.direction_correct,
            }
            for c in backtest.checkpoints
        ],
    }


def _get_cached_backtest(snap: FinancialSnapshot, view: str) -> dict:
    key = _backtest_cache_key(snap.ticker, view)
    cached = cache_get_json(key)
    if isinstance(cached, dict):
        return cached
    payload = _serialise_backtest(run_backtest(snap))
    cache_set_json(key, payload)
    return payload


def _get_cached_peer(sector: str, ticker: str) -> dict:
    if not sector:
        return {"average_pe": None, "peers_used": 0, "peers_considered": 0}
    key = _peer_cache_key(sector, ticker)
    cached = cache_get_json(key)
    if isinstance(cached, dict):
        return cached
    payload = fetch_peer_average_pe(sector, ticker)
    cache_set_json(key, payload)
    return payload


@router.get("/search")
def search(q: str = Query(..., min_length=1, description="Ticker or company name fragment")):
    return {"query": q, "results": search_tickers(q)}


@router.get("/valuation/{ticker}")
def get_valuation(
    ticker: str,
    dcf_view: str = Query("yfinance", description="Which valuation tab to load: yfinance or fmp"),
    growth_rate: Optional[float] = Query(None, description="Annual revenue growth rate, e.g. 0.05 for 5%"),
    discount_rate: Optional[float] = Query(None, description="DCF discount rate, e.g. 0.09 for 9%"),
    risk_free_rate: Optional[float] = Query(None, description="Risk-free rate used in CAPM, e.g. 0.045 for 4.5%"),
    beta: Optional[float] = Query(None, description="Beta used in CAPM"),
    equity_risk_premium: Optional[float] = Query(None, description="Equity risk premium used in CAPM"),
    cost_of_debt: Optional[float] = Query(None, description="Pre-tax cost of debt used in WACC, e.g. 0.045 for 4.5%"),
    debt_weight: Optional[float] = Query(None, description="Debt weight in capital structure, D/(D+E), e.g. 0.18"),
    ebit_margin: Optional[float] = Query(None, description="EBIT margin, e.g. 0.25 for 25% of revenue"),
    tax_rate: Optional[float] = Query(None, description="Effective tax rate, e.g. 0.21 for 21%"),
    da_pct: Optional[float] = Query(None, description="Depreciation & amortization as % of revenue"),
    capex_pct: Optional[float] = Query(None, description="Capital expenditure as % of revenue"),
    nwc_pct: Optional[float] = Query(None, description="Working capital change as % of revenue"),
    terminal_growth: Optional[float] = Query(None, description="Perpetuity growth rate after year 5"),
):
    view = (dcf_view or "fmp").strip().lower()
    if view not in {"fmp", "yfinance"}:
        raise HTTPException(status_code=400, detail="dcf_view must be either 'fmp' or 'yfinance'")

    try:
        # Cached for 6 hours by default. Manual assumption changes and another
        # user searching the same ticker/view reuse this base data instead of
        # calling Yahoo/SEC/FMP again.
        snap = _fetch_snapshot_cached(ticker, view)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"could not fetch data for '{ticker}': {exc}")

    # Do not spend FMP quota from the Yahoo/Internal DCF tab. FMP is touched
    # only when the user explicitly opens the FMP DCF tab. This keeps the
    # default free-data workflow usable for unlimited Yahoo searches.
    if view == "fmp" and snap.data_source != "Financial Modeling Prep" and "." in ticker and snap.revenue_history and snap.ebit_history:
        fmp_warning = cross_check_against_fmp(ticker, snap.revenue_history[-1], snap.ebit_history[-1])
        if fmp_warning:
            snap.data_warnings.append(fmp_warning)

    suitability = check_suitability(snap)
    default_risk_free_rate = fetch_risk_free_rate_for_currency(snap.currency)
    defaults = dcf.default_assumptions(snap, default_risk_free_rate)

    overrides = {
        "growth_rate": growth_rate,
        "discount_rate": discount_rate,
        "risk_free_rate": risk_free_rate,
        "beta": beta,
        "equity_risk_premium": equity_risk_premium,
        "cost_of_debt": cost_of_debt,
        "debt_weight": debt_weight,
        "ebit_margin": ebit_margin,
        "tax_rate": tax_rate,
        "da_pct": da_pct,
        "capex_pct": capex_pct,
        "nwc_pct": nwc_pct,
        "terminal_growth": terminal_growth,
    }
    assumptions = dcf.apply_overrides(defaults, overrides)

    try:
        result = dcf.run_valuation(snap, assumptions)
        sensitivity = dcf.build_sensitivity_grid(snap, assumptions)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if view == "fmp" and fmp_is_configured():
        # Only the FMP tab fetches FMP's prebuilt DCF. The Yahoo tab must stay
        # free-data-only and must not spend FMP quota in the background.
        fmp_benchmark = fetch_fmp_dcf_benchmarks(snap.ticker)
    else:
        fmp_benchmark = {
            "configured": fmp_is_configured(),
            "discounted_cash_flow": None,
            "levered_dcf": None,
            "source": "Financial Modeling Prep",
        }

    fmp_standard_value = (fmp_benchmark.get("discounted_cash_flow") or {}).get("dcf")
    fmp_levered_value = (fmp_benchmark.get("levered_dcf") or {}).get("dcf")
    if fmp_standard_value:
        fmp_benchmark["wacc_to_match_standard_dcf"] = dcf.solve_discount_rate_for_target_price(
            snap, assumptions, fmp_standard_value
        )
    else:
        fmp_benchmark["wacc_to_match_standard_dcf"] = None
    if fmp_levered_value:
        fmp_benchmark["wacc_to_match_levered_dcf"] = dcf.solve_discount_rate_for_target_price(
            snap, assumptions, fmp_levered_value
        )
    else:
        fmp_benchmark["wacc_to_match_levered_dcf"] = None

    internal_result = result
    fmp_direct_item = fmp_benchmark.get("discounted_cash_flow") or fmp_benchmark.get("levered_dcf")
    fmp_direct_value = (fmp_direct_item or {}).get("dcf")
    if view == "fmp" and fmp_is_configured() and _fmp_direct_dcf_enabled() and fmp_direct_value:
        # Headline mode: use FMP's prebuilt DCF value as the fair value so the
        # app matches the FMP website/API. Keep the internal DCF result for
        # charts/assumption diagnostics, because those are transparent and user-editable.
        current_price_for_gap = snap.current_price or (fmp_direct_item or {}).get("stock_price") or 0.0
        gap = ((fmp_direct_value - current_price_for_gap) / current_price_for_gap * 100) if current_price_for_gap else 0.0
        result = dcf.ValuationResult(
            fair_value_per_share=float(fmp_direct_value),
            current_price=float(current_price_for_gap),
            gap_percent=gap,
            verdict=_verdict_from_gap(gap),
            projected_fcfe=internal_result.projected_fcfe,
            discounted_fcfe=internal_result.discounted_fcfe,
            terminal_value_discounted=internal_result.terminal_value_discounted,
            years=internal_result.years,
            enterprise_value=internal_result.enterprise_value,
            equity_value=internal_result.equity_value,
            terminal_value_share=internal_result.terminal_value_share,
            health_flags=internal_result.health_flags,
        )
        snap.data_warnings.append(
            "Headline fair value is using FMP's prebuilt DCF endpoint. The assumptions, projected FCFF, "
            "sensitivity table, and reverse-DCF diagnostics still show the app's transparent internal model, "
            "so they will not reconcile exactly to the headline FMP DCF value."
        )
        snap.data_source = "Financial Modeling Prep DCF"

    # Recompute diagnostics after the optional FMP-direct headline override.
    PLAUSIBLE_GAP_THRESHOLD = 150.0
    gap_ok = abs(result.gap_percent) <= PLAUSIBLE_GAP_THRESHOLD
    fair_value_meaningful = result.fair_value_per_share > 0
    reliability_confident = gap_ok and fair_value_meaningful
    reliability_reason = None
    if not reliability_confident:
        if not fair_value_meaningful:
            reliability_reason = (
                "The model produced a negative intrinsic value because projected free cash flow is "
                "persistently negative. A DCF is not meaningful for a business not expected to generate "
                "positive cash flow over the forecast period."
            )
        else:
            reliability_reason = (
                f"The computed gap versus market price is {abs(result.gap_percent):.0f}%, which is far "
                "beyond what a normal valuation disagreement looks like. This usually signals a data or "
                "assumption problem (a misclassified financial line item, an unresolved currency mismatch, "
                "or a one-off event distorting a historical average) rather than a genuine mispricing. "
                "Check the assumptions panel for anything that looks implausible before trusting this number."
            )

    for flag in result.health_flags or []:
        if flag not in snap.data_warnings:
            snap.data_warnings.append(flag)

    implied_pe = (
        result.fair_value_per_share / snap.trailing_eps
        if snap.trailing_eps and snap.trailing_eps > 0
        else None
    )
    implied_growth_rate = dcf.solve_implied_growth_rate(snap, assumptions)
    implied_discount_rate = dcf.solve_implied_discount_rate(snap, assumptions)

    # A large price/value gap is not automatically a data bug. For high-quality
    # compounders such as large software/platform businesses, the market may be
    # underwriting much lower long-run returns or much stronger growth than a
    # conservative historical-average DCF. Surface this as a reverse-DCF
    # diagnostic so the user knows what assumption would have to change.
    if (
        implied_discount_rate is not None
        and abs(result.gap_percent) > 30
        and implied_discount_rate < assumptions.discount_rate - 0.02
    ):
        snap.data_warnings.append(
            "Reverse DCF check: holding these cash-flow assumptions fixed, the current market price "
            f"implies a WACC of about {implied_discount_rate * 100:.1f}%, versus your model WACC of "
            f"{assumptions.discount_rate * 100:.1f}%. The low fair value is therefore mainly an "
            "assumption disagreement, not necessarily a broken formula."
        )

    peer = _get_cached_peer(snap.sector or "", snap.ticker)
    backtest_payload = _get_cached_backtest(snap, view)

    return {
        "ticker": snap.ticker,
        "company_name": snap.company_name,
        "sector": snap.sector,
        "industry": snap.industry,
        "currency": snap.currency,
        "data_source": snap.data_source,
        "dcf_view": view,
        "suitability": {
            "suitable": suitability.suitable,
            "reasons": suitability.reasons,
        },
        "data_warnings": snap.data_warnings,
        "default_assumptions": {
            "growth_rate": defaults.growth_rate,
            "discount_rate": defaults.discount_rate,
            "risk_free_rate": defaults.risk_free_rate,
            "beta": defaults.beta,
            "equity_risk_premium": defaults.equity_risk_premium,
            "cost_of_debt": defaults.cost_of_debt,
            "debt_weight": defaults.debt_weight,
            "cost_of_equity": defaults.cost_of_equity,
            "ebit_margin": defaults.ebit_margin,
            "tax_rate": defaults.tax_rate,
            "da_pct": defaults.da_pct,
            "capex_pct": defaults.capex_pct,
            "nwc_pct": defaults.nwc_pct,
            "terminal_growth": defaults.terminal_growth,
        },
        "assumptions": {
            "growth_rate": assumptions.growth_rate,
            "discount_rate": assumptions.discount_rate,
            "risk_free_rate": assumptions.risk_free_rate,
            "beta": assumptions.beta,
            "equity_risk_premium": assumptions.equity_risk_premium,
            "cost_of_debt": assumptions.cost_of_debt,
            "debt_weight": assumptions.debt_weight,
            "cost_of_equity": assumptions.cost_of_equity,
            "ebit_margin": assumptions.ebit_margin,
            "tax_rate": assumptions.tax_rate,
            "da_pct": assumptions.da_pct,
            "capex_pct": assumptions.capex_pct,
            "nwc_pct": assumptions.nwc_pct,
            "terminal_growth": assumptions.terminal_growth,
        },
        "overrides": {field: overrides[field] is not None for field in OVERRIDABLE_FIELDS},
        "valuation": {
            "fair_value_per_share": round(result.fair_value_per_share, 2),
            "current_price": round(result.current_price, 2),
            "gap_percent": round(result.gap_percent, 1),
            "verdict": result.verdict,
        },
        "reliability": {
            "confident": reliability_confident,
            "reason": reliability_reason,
        },
        "projection": {
            "years": result.years,
            "projected_fcfe": [round(v, 1) for v in result.projected_fcfe],
            "discounted_fcfe": [round(v, 1) for v in result.discounted_fcfe],
            "terminal_value_discounted": round(result.terminal_value_discounted, 1),
            "terminal_value_share": round(result.terminal_value_share, 3),
        },
        "sensitivity": sensitivity,
        "fmp_benchmark": fmp_benchmark,
        "multiples": {
            "trailing_pe": snap.trailing_pe,
            "ev_to_ebitda": snap.ev_to_ebitda,
            "price_to_sales": snap.price_to_sales,
            "dcf_implied_pe": round(implied_pe, 1) if implied_pe else None,
            "sector_peer_average_pe": round(peer["average_pe"], 1) if peer["average_pe"] else None,
            "peer_data_points": peer["peers_used"],
            "implied_growth_rate": round(implied_growth_rate, 4) if implied_growth_rate is not None else None,
            "implied_discount_rate": round(implied_discount_rate, 4) if implied_discount_rate is not None else None,
            "your_growth_rate": assumptions.growth_rate,
            "your_discount_rate": assumptions.discount_rate,
        },
        "backtest": backtest_payload,
    }


@router.get("/price-history/{ticker}")
def get_price_history(ticker: str, years: int = Query(5, ge=1, le=10)):
    source_pref = "fmp" if fmp_is_configured() and _fmp_price_history_enabled() else "yahoo"
    key = _price_history_cache_key(ticker, years, source_pref)
    cached = cache_get_json(key)
    if isinstance(cached, dict) and cached.get("history"):
        return cached

    source = "Yahoo Finance"
    try:
        history = None
        if fmp_is_configured() and _fmp_price_history_enabled():
            history = fetch_fmp_price_history(ticker, years=years)
            source = "Financial Modeling Prep"
        # To protect FMP quota, the chart uses Yahoo by default. Set
        # FMP_PRICE_HISTORY=1 only if you explicitly want FMP chart data.
        if not history:
            history = fetch_price_history(ticker, years=years)
            source = "Yahoo Finance fallback" if fmp_is_configured() and _fmp_price_history_enabled() else "Yahoo Finance"
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"could not fetch price history for '{ticker}': {exc}")
    if not history:
        raise HTTPException(status_code=404, detail=f"no price history available for '{ticker}'")
    payload = {"ticker": ticker.upper(), "history": history, "source": source}
    cache_set_json(key, payload)
    return payload


@router.get("/debug/fmp/{ticker}")
def debug_fmp(ticker: str):
    return debug_fmp_snapshot_status(ticker)


@router.get("/health")
def health():
    backup_key_2 = bool(os.environ.get("FMP_API_KEY_2") or os.environ.get("FMP_SECONDARY_API_KEY"))
    backup_key_3 = bool(os.environ.get("FMP_API_KEY_3") or os.environ.get("FMP_TERTIARY_API_KEY"))
    return {
        "status": "ok",
        "fmp_configured": fmp_is_configured(),
        "fmp_backup_key_2_configured": backup_key_2,
        "fmp_backup_key_3_configured": backup_key_3,
        "cache": cache_stats(),
    }
