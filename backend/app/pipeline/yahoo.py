"""
Pulls raw financial statement data from Yahoo Finance via yfinance and
normalizes it into a FinancialSnapshot the DCF model can consume.

yfinance's exact row labels shift between versions and between companies
(some report "EBIT", others only "Operating Income"), so _safe_row tries
a short list of known aliases before giving up on a line item.

Currency handling: for cross-listed stocks (e.g. a Danish company's shares
also trading in Frankfurt), Yahoo reports the trading price in one currency
(`currency`) but the underlying financial statements in the company's home
reporting currency (`financialCurrency`). Per-share stats and ratios in
`info` (EPS, P/E, EV/EBITDA) are already normalized to the trading currency
by Yahoo, but the raw income statement, cash flow, and balance sheet line
items are not. Mixing the two without converting produces fair values off
by whatever the FX rate between them is, which is silent and easy to miss.
This module detects that mismatch and converts the raw statement figures
using a live FX rate, or flags the snapshot as unreliable if no rate can
be fetched, rather than showing a confidently wrong number either way.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import yfinance as yf


@dataclass
class FinancialSnapshot:
    ticker: str
    company_name: str
    sector: Optional[str]
    industry: Optional[str]
    currency: str
    current_price: float
    shares_outstanding: float
    beta: Optional[float]
    total_debt: float
    cash_and_equivalents: float
    revenue_history: list        # oldest -> newest
    ebit_history: list
    tax_paid_history: list
    pretax_income_history: list
    da_history: list
    capex_history: list
    nwc_change_history: list
    interest_expense_history: list
    years: list
    period_end_dates: list       # ISO date strings, oldest -> newest, same length as years
    total_debt_history: list = field(default_factory=list)
    cash_and_equivalents_history: list = field(default_factory=list)
    trailing_pe: Optional[float] = None
    ev_to_ebitda: Optional[float] = None
    price_to_sales: Optional[float] = None
    trailing_eps: Optional[float] = None
    financial_currency: Optional[str] = None
    currency_mismatch_unresolved: bool = False
    data_source: str = "Yahoo Finance"
    data_warnings: list = field(default_factory=list)


def _safe_row(df, *labels):
    """Return the first matching row as a list ordered oldest -> newest,
    trying each label in turn. Returns [] if none of the labels exist."""
    if df is None or df.empty:
        return []
    for label in labels:
        if label in df.index:
            row = df.loc[label]
            return list(reversed(row.dropna().tolist()))
    return []


def fetch_fx_rate(from_currency: str, to_currency: str) -> Optional[float]:
    """Live rate to convert an amount in from_currency into to_currency
    (i.e. multiply by this to convert). Returns None if unavailable."""
    if not from_currency or not to_currency or from_currency == to_currency:
        return 1.0
    try:
        pair = yf.Ticker(f"{from_currency}{to_currency}=X")
        hist = pair.history(period="5d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return None


def fetch_financial_snapshot(ticker_symbol: str) -> FinancialSnapshot:
    t = yf.Ticker(ticker_symbol)
    info = t.info or {}
    warnings = []

    income = t.financials
    cashflow = t.cashflow
    balance = t.balance_sheet

    if income is None or income.empty:
        raise ValueError(f"no income statement data available for '{ticker_symbol}'")

    columns_oldest_first = list(income.columns)[::-1]
    years = [str(c.year) for c in columns_oldest_first]
    period_end_dates = [c.strftime("%Y-%m-%d") for c in columns_oldest_first]

    revenue = _safe_row(income, "Total Revenue", "Operating Revenue")
    ebit = _safe_row(income, "EBIT", "Operating Income")
    pretax = _safe_row(income, "Pretax Income")
    tax = _safe_row(income, "Tax Provision")
    # Yahoo can return interest expense as either positive or negative depending
    # on the company/source. For modelling ratios, keep it as a positive cost.
    interest = [abs(v) for v in _safe_row(income, "Interest Expense")]

    # These are raw cash-flow statement rows. Normalize signs to DCF convention:
    # - D&A is a positive add-back
    # - CapEx may be negative in Yahoo; the DCF layer takes abs() when making the ratio
    # - Change in working capital in Yahoo is usually the cash-flow effect
    #   (positive = source of cash). Convert it to DCF convention, where positive
    #   means extra cash tied up in working capital and should be subtracted.
    da = [abs(v) for v in _safe_row(cashflow, "Depreciation And Amortization", "Depreciation Amortization Depletion")]
    capex = _safe_row(cashflow, "Capital Expenditure")
    nwc_cashflow_effect = _safe_row(cashflow, "Change In Working Capital")
    nwc = [-v for v in nwc_cashflow_effect]

    # Company-level statements must be divided by company-level shares. Yahoo's
    # info["sharesOutstanding"] can be ticker/share-class specific for dual-class
    # companies, which makes fair value per share wildly wrong. Prefer the latest
    # diluted/basic average shares from the income statement when available because
    # it aligns with the company-level financials used in the DCF.
    statement_shares_history = _safe_row(income, "Diluted Average Shares", "Basic Average Shares")
    latest_statement_shares = statement_shares_history[-1] if statement_shares_history else 0.0

    if not da:
        warnings.append("Depreciation and amortization not found in reported data, defaulted to 0")
    if not capex:
        warnings.append("Capital expenditure not found in reported data, defaulted to 0")
    if not nwc:
        warnings.append("Working capital change not found in reported data, defaulted to 0")

    total_debt = 0.0
    cash = 0.0
    debt_history = []
    cash_history = []
    if balance is not None and not balance.empty:
        debt_history = _safe_row(balance, "Total Debt")
        cash_history = _safe_row(
            balance, "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"
        )
        total_debt = debt_history[-1] if debt_history else 0.0
        cash = cash_history[-1] if cash_history else 0.0

    quote_shares = info.get("sharesOutstanding") or 0.0
    shares = latest_statement_shares or quote_shares
    price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose") or 0.0

    if latest_statement_shares and quote_shares:
        diff = abs(latest_statement_shares - quote_shares) / max(latest_statement_shares, quote_shares)
        if diff > 0.05:
            warnings.append(
                "Using diluted/basic average shares from the financial statements because those shares "
                "align with company-level cash flows. Yahoo quote shares differed by "
                f"{diff * 100:.0f}%, which often happens for dual-class or non-US tickers."
            )

    if not shares:
        warnings.append("Shares outstanding missing, per-share value cannot be computed reliably")
    if not price:
        warnings.append("Current market price unavailable")

    trading_currency = info.get("currency") or "USD"
    financial_currency = info.get("financialCurrency") or trading_currency
    currency_mismatch_unresolved = False

    if financial_currency != trading_currency:
        fx_rate = fetch_fx_rate(financial_currency, trading_currency)
        if fx_rate is not None:
            revenue = [v * fx_rate for v in revenue]
            ebit = [v * fx_rate for v in ebit]
            pretax = [v * fx_rate for v in pretax]
            tax = [v * fx_rate for v in tax]
            interest = [v * fx_rate for v in interest]
            da = [v * fx_rate for v in da]
            capex = [v * fx_rate for v in capex]
            nwc = [v * fx_rate for v in nwc]
            debt_history = [v * fx_rate for v in debt_history]
            cash_history = [v * fx_rate for v in cash_history]
            total_debt = total_debt * fx_rate
            cash = cash * fx_rate
            warnings.append(
                f"Financial statements are reported in {financial_currency} but this ticker trades in "
                f"{trading_currency}. Converted using a live rate of 1 {financial_currency} = "
                f"{fx_rate:.4f} {trading_currency}."
            )
        else:
            currency_mismatch_unresolved = True
            warnings.append(
                f"Financial statements are reported in {financial_currency} but this ticker trades in "
                f"{trading_currency}, and a live FX rate to convert between them could not be fetched. "
                "The figures below mix two currencies and are not reliable."
            )

    return FinancialSnapshot(
        ticker=ticker_symbol.upper(),
        company_name=info.get("longName") or info.get("shortName") or ticker_symbol.upper(),
        sector=info.get("sector"),
        industry=info.get("industry"),
        currency=trading_currency,
        current_price=float(price),
        shares_outstanding=float(shares),
        beta=info.get("beta"),
        total_debt=float(total_debt),
        cash_and_equivalents=float(cash),
        revenue_history=revenue,
        ebit_history=ebit,
        tax_paid_history=tax,
        pretax_income_history=pretax,
        da_history=da,
        capex_history=capex,
        nwc_change_history=nwc,
        interest_expense_history=interest,
        years=years,
        period_end_dates=period_end_dates,
        total_debt_history=[float(v) for v in debt_history],
        cash_and_equivalents_history=[float(v) for v in cash_history],
        trailing_pe=info.get("trailingPE"),
        ev_to_ebitda=info.get("enterpriseToEbitda"),
        price_to_sales=info.get("priceToSalesTrailing12Months"),
        trailing_eps=info.get("trailingEps"),
        financial_currency=financial_currency,
        currency_mismatch_unresolved=currency_mismatch_unresolved,
        data_warnings=warnings,
    )


def fetch_risk_free_rate() -> float:
    """10-year US Treasury yield, sourced from Yahoo's ^TNX index (already
    quoted in percent, e.g. a Close of 4.32 means 4.32%). Falls back to a
    fixed 4.5% if the fetch fails, so the app degrades gracefully."""
    try:
        tnx = yf.Ticker("^TNX")
        hist = tnx.history(period="5d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1]) / 100.0
    except Exception:
        pass
    return 0.045


def fetch_risk_free_rate_as_of(date_str: str) -> float:
    """10-year Treasury yield around a past date, for the backtest feature.
    Widens the window until it finds a trading day, and falls back to
    today's rate if the historical fetch fails entirely."""
    try:
        as_of = datetime.strptime(date_str, "%Y-%m-%d")
        tnx = yf.Ticker("^TNX")
        hist = tnx.history(start=(as_of - timedelta(days=10)).strftime("%Y-%m-%d"),
                            end=(as_of + timedelta(days=10)).strftime("%Y-%m-%d"))
        if not hist.empty:
            return float(hist["Close"].iloc[-1]) / 100.0
    except Exception:
        pass
    return fetch_risk_free_rate()


def fetch_price_on_date(ticker_symbol: str, date_str: str) -> Optional[float]:
    """Closing price nearest a given past date. Returns None if unavailable."""
    try:
        as_of = datetime.strptime(date_str, "%Y-%m-%d")
        t = yf.Ticker(ticker_symbol)
        hist = t.history(
            start=(as_of - timedelta(days=10)).strftime("%Y-%m-%d"),
            end=(as_of + timedelta(days=10)).strftime("%Y-%m-%d"),
        )
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception:
        return None


def fetch_price_history(ticker_symbol: str, years: int = 5) -> list:
    """Weekly closing prices for the last N years, as [{date, close}, ...].
    Downsampled to weekly so the payload stays small."""
    t = yf.Ticker(ticker_symbol)
    hist = t.history(period=f"{years}y")
    if hist.empty:
        return []
    weekly = hist["Close"].resample("W").last().dropna()
    return [{"date": idx.strftime("%Y-%m-%d"), "close": round(float(val), 2)} for idx, val in weekly.items()]
