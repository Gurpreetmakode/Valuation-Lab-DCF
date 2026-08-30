"""
Backtest: recompute the DCF using only the financial data that would have
been available at several points in the past, then check whether the
price actually moved the direction each historical estimate expected.

One historical check is barely a data point, so this now runs at every
holdout window the free data allows (typically 1, 2, and 3 years back) and
reports a hit rate across all of them, not a single verdict dressed up as
one.

Honest limitations, stated up front rather than hidden:
- yfinance's free annual statement history is short (typically 4-5 years),
  so there are usually only 2-3 checkpoints available, not a large sample.
- Shares outstanding and beta use today's values as approximations for
  their historical values, since free point-in-time data for those is not
  reliably available. Historical debt, cash, and stock price are used where
  available so the WACC and EV-to-equity bridge are at least time-consistent.
These are the same kind of simplifications already documented for the
main DCF, just applied on shorter data windows, so this should be read as
directional evidence, not a rigorous track record.
"""

from dataclasses import dataclass, replace
from typing import Optional

from app.models import dcf
from app.pipeline.fmp import fetch_fmp_price_on_date
from app.pipeline.yahoo import (
    FinancialSnapshot,
    fetch_price_on_date,
    fetch_risk_free_rate_as_of,
)

MIN_CUT = 2
MAX_CHECKPOINTS = 3


@dataclass
class BacktestCheckpoint:
    as_of_date: str
    implied_fair_value_then: float
    actual_price_then: float
    price_change_pct: float
    model_gap_then_pct: float
    direction_correct: bool


@dataclass
class BacktestSummary:
    available: bool
    reason: Optional[str]
    checkpoints: list
    correct_count: int
    total_count: int
    actual_price_now: Optional[float] = None


def _historical_scalar(history: list, cut: int, fallback: float) -> float:
    if history and len(history) >= cut and history[cut - 1] is not None:
        return float(history[cut - 1])
    if history and len(history) < cut and history[-1] is not None:
        # Better than zero if the free data source supplies fewer balance-sheet
        # years than income-statement years, but still an approximation.
        return float(history[-1])
    return float(fallback or 0.0)


def _truncate(snap: FinancialSnapshot, cut: int) -> FinancialSnapshot:
    debt_history = getattr(snap, "total_debt_history", None) or []
    cash_history = getattr(snap, "cash_and_equivalents_history", None) or []
    return replace(
        snap,
        revenue_history=snap.revenue_history[:cut],
        ebit_history=snap.ebit_history[:cut],
        tax_paid_history=snap.tax_paid_history[:cut],
        pretax_income_history=snap.pretax_income_history[:cut],
        da_history=snap.da_history[:cut],
        capex_history=snap.capex_history[:cut],
        nwc_change_history=snap.nwc_change_history[:cut],
        interest_expense_history=snap.interest_expense_history[:cut],
        years=snap.years[:cut],
        period_end_dates=snap.period_end_dates[:cut],
        total_debt_history=debt_history[:cut],
        cash_and_equivalents_history=cash_history[:cut],
        total_debt=_historical_scalar(debt_history, cut, snap.total_debt),
        cash_and_equivalents=_historical_scalar(cash_history, cut, snap.cash_and_equivalents),
    )


def _run_checkpoint(snap: FinancialSnapshot, cut: int) -> Optional[BacktestCheckpoint]:
    historical_snap = _truncate(snap, cut)
    as_of_date = historical_snap.period_end_dates[-1]

    actual_price_then = fetch_fmp_price_on_date(snap.ticker, as_of_date) or fetch_price_on_date(snap.ticker, as_of_date)
    if actual_price_then is None or not snap.current_price:
        return None

    # Use the historical price for the historical capital-structure weight in
    # WACC. Leaving today's price here would make a 2023 backtest use a 2026
    # market-cap weight, which is the same timing bug as using today's debt/cash.
    historical_snap = replace(historical_snap, current_price=actual_price_then)

    historical_rf = fetch_risk_free_rate_as_of(as_of_date)
    historical_assumptions = dcf.default_assumptions(historical_snap, historical_rf)

    try:
        historical_result = dcf.run_valuation(historical_snap, historical_assumptions)
    except (ZeroDivisionError, ValueError):
        return None

    implied_fair_value_then = historical_result.fair_value_per_share

    price_change_pct = (snap.current_price - actual_price_then) / actual_price_then * 100
    model_gap_then_pct = (implied_fair_value_then - actual_price_then) / actual_price_then * 100

    model_said_undervalued = implied_fair_value_then > actual_price_then
    price_went_up = snap.current_price > actual_price_then
    direction_correct = model_said_undervalued == price_went_up

    return BacktestCheckpoint(
        as_of_date=as_of_date,
        implied_fair_value_then=round(implied_fair_value_then, 2),
        actual_price_then=round(actual_price_then, 2),
        price_change_pct=round(price_change_pct, 1),
        model_gap_then_pct=round(model_gap_then_pct, 1),
        direction_correct=direction_correct,
    )


def run_backtest(snap: FinancialSnapshot) -> BacktestSummary:
    if not snap.shares_outstanding:
        return BacktestSummary(
            available=False,
            reason="Shares outstanding unavailable, cannot compute a historical per-share value.",
            checkpoints=[],
            correct_count=0,
            total_count=0,
        )

    n = len(snap.revenue_history)
    checkpoints = []
    for holdout in range(1, MAX_CHECKPOINTS + 1):
        cut = n - holdout
        if cut < MIN_CUT:
            break
        checkpoint = _run_checkpoint(snap, cut)
        if checkpoint is not None:
            checkpoints.append(checkpoint)

    if not checkpoints:
        return BacktestSummary(
            available=False,
            reason="Not enough historical statement or price data to run a backtest for this ticker.",
            checkpoints=[],
            correct_count=0,
            total_count=0,
        )

    correct = sum(1 for c in checkpoints if c.direction_correct)
    return BacktestSummary(
        available=True,
        reason=None,
        checkpoints=checkpoints,
        correct_count=correct,
        total_count=len(checkpoints),
        actual_price_now=snap.current_price,
    )
