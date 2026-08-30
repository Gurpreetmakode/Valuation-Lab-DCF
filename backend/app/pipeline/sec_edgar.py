"""
SEC EDGAR as a fundamentals source for US-listed companies.

Unlike Yahoo Finance, EDGAR's XBRL data comes directly from a company's own
regulatory filings, tagged against a standardized taxonomy (US-GAAP), so
"revenue" means the same thing across every US filer rather than depending
on a data vendor's row-labeling guesswork. This is exactly the class of bug
that caused the EBIT-margin mismatch found earlier in this project. EDGAR
also naturally prefers the most recently *filed* value for a given fiscal
year, which sidesteps the "original vs restated" mismatch problem too,
since a company's own later filings supersede earlier ones by definition.

Requires no API key, only a descriptive User-Agent header (SEC's usage
policy requires this so they can identify high-volume or misbehaving
clients; it doesn't require registration).

This is best-effort and US-only: if the ticker can't be mapped to a CIK,
or the expected XBRL concepts aren't present in a usable shape, callers
should fall back to the yfinance-based pipeline rather than fail outright.
"""

from typing import Optional

import requests

_HEADERS = {"User-Agent": "Intrinsic Valuation App (contact: set-your-email-here@example.com)"}
_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# Concepts tried in order for each line item, since different filers (and
# different US-GAAP taxonomy vintages) use different tags for the same
# underlying concept.
CONCEPT_CANDIDATES = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "ebit": ["OperatingIncomeLoss"],
    "pretax_income": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
    "tax": ["IncomeTaxExpenseBenefit"],
    "da": ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet", "DepreciationAndAmortization"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "interest": ["InterestExpense", "InterestExpenseDebt"],
    "total_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
}

_cik_map_cache: Optional[dict] = None


def _load_ticker_to_cik_map() -> dict:
    global _cik_map_cache
    if _cik_map_cache is not None:
        return _cik_map_cache
    response = requests.get(_TICKER_MAP_URL, headers=_HEADERS, timeout=10)
    response.raise_for_status()
    raw = response.json()  # {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
    _cik_map_cache = {entry["ticker"].upper(): str(entry["cik_str"]).zfill(10) for entry in raw.values()}
    return _cik_map_cache


def fetch_cik_for_ticker(ticker: str) -> Optional[str]:
    try:
        mapping = _load_ticker_to_cik_map()
        return mapping.get(ticker.upper())
    except Exception:
        return None


def _annual_series(facts: dict, concept_candidates: list, is_instant: bool) -> dict:
    """Returns {fiscal_year_end_date: value}, preferring the most recently
    *filed* figure for each fiscal year end when a year is reported more
    than once (e.g. as a prior-year comparative in a later filing)."""
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    for concept in concept_candidates:
        node = us_gaap.get(concept)
        if not node:
            continue
        usd_entries = node.get("units", {}).get("USD", [])
        best_by_end_date: dict = {}
        for entry in usd_entries:
            if entry.get("form") != "10-K":
                continue
            if not is_instant and entry.get("fp") != "FY":
                continue
            end_date = entry.get("end")
            if not end_date:
                continue
            if not is_instant:
                # keep only genuine ~1-year duration facts, not quarterly or YTD fragments
                start_date = entry.get("start")
                if not start_date:
                    continue
            filed = entry.get("filed", "")
            existing = best_by_end_date.get(end_date)
            if existing is None or filed > existing[1]:
                best_by_end_date[end_date] = (entry.get("val"), filed)
        if best_by_end_date:
            return {date: val for date, (val, _filed) in best_by_end_date.items()}
    return {}


def fetch_sec_financials(ticker: str, max_years: int = 5) -> Optional[dict]:
    """Returns a dict of parallel oldest->newest lists matching
    FinancialSnapshot's history fields, or None if EDGAR doesn't have
    enough usable data for this ticker (private company, recent IPO with
    too little history, unusual filer type, etc.)."""
    cik = fetch_cik_for_ticker(ticker)
    if not cik:
        return None

    try:
        response = requests.get(_COMPANY_FACTS_URL.format(cik=cik), headers=_HEADERS, timeout=10)
        response.raise_for_status()
        facts = response.json()
    except Exception:
        return None

    revenue_by_date = _annual_series(facts, CONCEPT_CANDIDATES["revenue"], is_instant=False)
    ebit_by_date = _annual_series(facts, CONCEPT_CANDIDATES["ebit"], is_instant=False)

    # revenue and EBIT are the two fields the model cannot function without;
    # everything else defaults to 0 for a given year if missing, same as
    # the yfinance pipeline already does
    common_dates = sorted(set(revenue_by_date) & set(ebit_by_date))
    if len(common_dates) < 3:
        return None
    common_dates = common_dates[-max_years:]

    pretax_by_date = _annual_series(facts, CONCEPT_CANDIDATES["pretax_income"], is_instant=False)
    tax_by_date = _annual_series(facts, CONCEPT_CANDIDATES["tax"], is_instant=False)
    da_by_date = _annual_series(facts, CONCEPT_CANDIDATES["da"], is_instant=False)
    capex_by_date = _annual_series(facts, CONCEPT_CANDIDATES["capex"], is_instant=False)
    interest_by_date = _annual_series(facts, CONCEPT_CANDIDATES["interest"], is_instant=False)
    debt_by_date = _annual_series(facts, CONCEPT_CANDIDATES["total_debt"], is_instant=True)
    cash_by_date = _annual_series(facts, CONCEPT_CANDIDATES["cash"], is_instant=True)

    def series(by_date: dict) -> list:
        return [by_date.get(d, 0.0) for d in common_dates]

    latest = common_dates[-1]
    debt_history = series(debt_by_date)
    cash_history = series(cash_by_date)
    return {
        "years": [d[:4] for d in common_dates],
        "period_end_dates": common_dates,
        "revenue_history": series(revenue_by_date),
        "ebit_history": series(ebit_by_date),
        "pretax_income_history": series(pretax_by_date),
        "tax_paid_history": series(tax_by_date),
        "da_history": series(da_by_date),
        # SEC CapEx is reported as a positive outflow; yfinance's convention
        # (used elsewhere in this codebase) is negative, so flip the sign
        # here to keep the two sources interchangeable downstream
        "capex_history": [-v for v in series(capex_by_date)],
        "nwc_change_history": [0.0] * len(common_dates),  # not a single clean XBRL concept; left to yfinance's cashflow line when available
        "interest_expense_history": series(interest_by_date),
        "total_debt_history": debt_history,
        "cash_and_equivalents_history": cash_history,
        "total_debt": debt_by_date.get(latest, 0.0),
        "cash_and_equivalents": cash_by_date.get(latest, 0.0),
    }
