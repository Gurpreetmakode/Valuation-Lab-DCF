"""Financial snapshot router.

This FMP-only build uses Financial Modeling Prep as the primary required
company-data source whenever FMP_API_KEY is configured. If FMP is configured
but returns no usable statement data, the app raises a clear error instead of
silently falling back to SEC EDGAR/yfinance and showing a misleading SEC badge.

If you remove FMP_API_KEY, the old free SEC EDGAR + yfinance fallback still
works so the project remains runnable without credentials.
"""

from __future__ import annotations

import os
from dataclasses import replace

from app.pipeline import fmp, sec_edgar, yahoo


def _fmp_only_enabled() -> bool:
    return os.environ.get("FMP_ONLY", "1").strip().lower() not in {"0", "false", "no", "off"}


def fetch_financial_snapshot_hybrid(ticker: str) -> yahoo.FinancialSnapshot:
    # FMP first. In this build, when a key exists, do not silently fall back to
    # SEC/yfinance; that is exactly why the UI kept showing "SEC EDGAR".
    if fmp.is_configured():
        fmp_snap = fmp.fetch_fmp_financial_snapshot(ticker)
        if fmp_snap is not None:
            return fmp_snap

        if _fmp_only_enabled():
            raise RuntimeError(
                "FMP_API_KEY is configured, but FMP did not return enough usable statement data "
                f"for {ticker.upper()}. Check that backend/.env is loaded, the key is valid, "
                "your FMP plan allows income-statement/balance-sheet/cash-flow endpoints, "
                "and the symbol is correct. Because FMP_ONLY=1, the app did not fall back to SEC EDGAR."
            )

    # No FMP key, or FMP_ONLY=0: keep the original no-signup fallback.
    snap = yahoo.fetch_financial_snapshot(ticker)

    # SEC EDGAR only covers US-listed/company filings well. If the ticker has an
    # exchange suffix, keep Yahoo's exchange-aware data rather than trying to
    # map it to a US CIK.
    if "." in ticker:
        return snap

    sec_data = sec_edgar.fetch_sec_financials(ticker)
    if not sec_data:
        return snap

    return replace(
        snap,
        years=sec_data["years"],
        period_end_dates=sec_data["period_end_dates"],
        revenue_history=sec_data["revenue_history"],
        ebit_history=sec_data["ebit_history"],
        pretax_income_history=sec_data["pretax_income_history"],
        tax_paid_history=sec_data["tax_paid_history"],
        da_history=sec_data["da_history"],
        capex_history=sec_data["capex_history"],
        nwc_change_history=sec_data["nwc_change_history"],
        interest_expense_history=sec_data["interest_expense_history"],
        total_debt_history=sec_data.get("total_debt_history") or snap.total_debt_history,
        cash_and_equivalents_history=sec_data.get("cash_and_equivalents_history") or snap.cash_and_equivalents_history,
        total_debt=sec_data["total_debt"] or snap.total_debt,
        cash_and_equivalents=sec_data["cash_and_equivalents"] or snap.cash_and_equivalents,
        data_source="SEC EDGAR",
    )
