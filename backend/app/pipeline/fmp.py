"""
Financial Modeling Prep helpers.

FMP now has two roles in the app:
1. Primary financial/market-data source when FMP_API_KEY is configured.
2. Optional benchmark for FMP's own prebuilt DCF outputs.

The app still keeps an internal transparent DCF. Using FMP as the primary
source fixes many yfinance problems (row-label drift, missing fields, odd
share counts, currency mismatches), but it does not make the internal DCF
match the market price. That still depends on growth, margin, WACC and
terminal-value assumptions.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

import requests

from app.cache import get_json as cache_get_json, make_key as cache_make_key, set_json as cache_set_json
from app.pipeline.yahoo import FinancialSnapshot

LEGACY_BASE_URL = "https://financialmodelingprep.com/api/v3"
STABLE_BASE_URL = "https://financialmodelingprep.com/stable"
DISAGREEMENT_THRESHOLD = 0.15  # flag when the two sources differ by more than 15%


def is_configured() -> bool:
    return bool(os.environ.get("FMP_API_KEY"))


def _api_keys() -> list[str]:
    """Return FMP keys in priority order.

    FMP_API_KEY is always the primary key. FMP_API_KEY_2 is attempted only
    after the primary key returns a quota/rate-limit error. FMP_API_KEY_3 is
    attempted only after the first two keys return quota/rate-limit errors.

    Backup keys are deliberately not used for invalid symbols, blocked
    endpoints, network failures, parsing errors, or normal empty responses.
    """
    raw_keys = [
        os.environ.get("FMP_API_KEY"),
        os.environ.get("FMP_API_KEY_2") or os.environ.get("FMP_SECONDARY_API_KEY"),
        os.environ.get("FMP_API_KEY_3") or os.environ.get("FMP_TERTIARY_API_KEY"),
    ]

    keys: list[str] = []
    for raw_key in raw_keys:
        if not raw_key:
            continue
        key = raw_key.strip()
        if not key:
            continue
        lower_key = key.lower()
        if "your_" in lower_key or "paste_" in lower_key or "placeholder" in lower_key:
            continue
        if key not in keys:
            keys.append(key)
    return keys


LAST_FMP_ERROR: Optional[str] = None


def _cache_key(url: str, params: Optional[dict]) -> str:
    # Important: params here never include the API key. This means once one key
    # has fetched a ticker/endpoint, later users and later manual recalculations
    # can reuse the cached data without spending another FMP call.
    clean_params = tuple(sorted((str(k), str(v)) for k, v in (params or {}).items()))
    return cache_make_key("fmp-json", url, clean_params)


def _from_cache(url: str, params: Optional[dict]):
    return cache_get_json(_cache_key(url, params))


def _save_cache(url: str, params: Optional[dict], data):
    cache_set_json(_cache_key(url, params), data)


def _quota_limited_text(text: str) -> bool:
    text = (text or "").lower()
    needles = ["rate limit", "too many", "quota", "limit reached", "limit reach", "daily limit", "api calls"]
    return any(needle in text for needle in needles)


def _response_is_quota_limited(response: requests.Response, data=None) -> bool:
    if response.status_code == 429:
        return True
    if isinstance(data, dict):
        joined = " ".join(str(v) for v in data.values() if v is not None)
        return _quota_limited_text(joined)
    if isinstance(data, list):
        return False
    return _quota_limited_text(response.text)


def _get_json(url: str, params: Optional[dict] = None, timeout: int = 12):
    """Fetch JSON from FMP with memory caching and quota-only key failover.

    Backup keys are deliberately conservative: key 2 is used only when key 1
    appears to have hit a quota/rate limit, and key 3 is used only when keys 1
    and 2 have both hit quota/rate limits. Other errors should be fixed, not
    hidden by burning backup keys.
    """
    global LAST_FMP_ERROR

    cached = _from_cache(url, params)
    if cached is not None:
        return cached

    keys = _api_keys()
    if not keys:
        LAST_FMP_ERROR = "FMP_API_KEY is missing from the backend environment."
        return None

    last_error = None
    for index, api_key in enumerate(keys):
        key_number = index + 1
        try:
            response = requests.get(url, params={**(params or {}), "apikey": api_key}, timeout=timeout)

            data = None
            try:
                data = response.json()
            except Exception:
                data = None

            if _response_is_quota_limited(response, data):
                last_error = f"{url} hit an FMP quota/rate limit using API key {key_number}."
                # Only quota/rate-limit errors may move on to the next key.
                if index < len(keys) - 1:
                    continue
                LAST_FMP_ERROR = last_error
                return None

            response.raise_for_status()

            if isinstance(data, dict) and data.get("Error Message"):
                LAST_FMP_ERROR = str(data.get("Error Message"))
                return None

            _save_cache(url, params, data)
            LAST_FMP_ERROR = None
            return data
        except Exception as exc:
            # Network/HTTP/JSON failures do not burn the backup key.
            last_error = f"{url} failed: {exc}"
            break

    LAST_FMP_ERROR = last_error
    return None


def _get_json_any(candidates: list[tuple[str, dict | None]], timeout: int = 12):
    """Try multiple FMP endpoint shapes.

    FMP currently shows many endpoints under /stable in its API viewer, while
    older examples use /api/v3. Trying both prevents a working key from being
    rejected just because one route family is unavailable on the user's plan.
    """
    for url, params in candidates:
        data = _get_json(url, params, timeout=timeout)
        if data:
            return data
    return None


def latest_error() -> Optional[str]:
    return LAST_FMP_ERROR


def _first(data):
    if isinstance(data, list) and data:
        return data[0]
    if isinstance(data, dict):
        return data
    return None


def _num(item: Optional[dict], *keys: str) -> Optional[float]:
    if not item:
        return None
    for key in keys:
        value = item.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _str(item: Optional[dict], *keys: str) -> Optional[str]:
    if not item:
        return None
    for key in keys:
        value = item.get(key)
        if value is not None and value != "":
            return str(value)
    return None


def _positive(value: Optional[float]) -> float:
    return abs(float(value)) if value is not None else 0.0


def _reverse_chronological(items: Optional[list], limit: int = 5) -> list:
    if not isinstance(items, list):
        return []
    usable = [item for item in items[:limit] if isinstance(item, dict)]
    return list(reversed(usable))  # oldest -> newest


def _safe_div(n: Optional[float], d: Optional[float]) -> Optional[float]:
    if n is None or d in (None, 0):
        return None
    return n / d


def _fetch_profile(ticker: str) -> Optional[dict]:
    symbol = ticker.upper()
    return _first(_get_json_any([
        (f"{STABLE_BASE_URL}/profile", {"symbol": symbol}),
        (f"{LEGACY_BASE_URL}/profile/{symbol}", None),
    ]))


def _fetch_quote(ticker: str) -> Optional[dict]:
    symbol = ticker.upper()
    return _first(_get_json_any([
        (f"{STABLE_BASE_URL}/quote", {"symbol": symbol}),
        (f"{LEGACY_BASE_URL}/quote/{symbol}", None),
    ]))


def _fetch_income_statements(ticker: str, limit: int = 5) -> list:
    symbol = ticker.upper()
    return _reverse_chronological(
        _get_json_any([
            (f"{STABLE_BASE_URL}/income-statement", {"symbol": symbol, "period": "annual", "limit": limit}),
            (f"{LEGACY_BASE_URL}/income-statement/{symbol}", {"period": "annual", "limit": limit}),
        ]),
        limit,
    )


def _fetch_balance_sheets(ticker: str, limit: int = 5) -> list:
    symbol = ticker.upper()
    return _reverse_chronological(
        _get_json_any([
            (f"{STABLE_BASE_URL}/balance-sheet-statement", {"symbol": symbol, "period": "annual", "limit": limit}),
            (f"{LEGACY_BASE_URL}/balance-sheet-statement/{symbol}", {"period": "annual", "limit": limit}),
        ]),
        limit,
    )


def _fetch_cash_flows(ticker: str, limit: int = 5) -> list:
    symbol = ticker.upper()
    return _reverse_chronological(
        _get_json_any([
            (f"{STABLE_BASE_URL}/cash-flow-statement", {"symbol": symbol, "period": "annual", "limit": limit}),
            (f"{LEGACY_BASE_URL}/cash-flow-statement/{symbol}", {"period": "annual", "limit": limit}),
        ]),
        limit,
    )


def _fetch_enterprise_values(ticker: str, limit: int = 5) -> list:
    symbol = ticker.upper()
    return _reverse_chronological(
        _get_json_any([
            (f"{STABLE_BASE_URL}/enterprise-values", {"symbol": symbol, "period": "annual", "limit": limit}),
            (f"{LEGACY_BASE_URL}/enterprise-values/{symbol}", {"period": "annual", "limit": limit}),
        ]),
        limit,
    )


def _fetch_ratios_ttm(ticker: str) -> Optional[dict]:
    symbol = ticker.upper()
    return _first(_get_json_any([
        (f"{STABLE_BASE_URL}/ratios-ttm", {"symbol": symbol}),
        (f"{LEGACY_BASE_URL}/ratios-ttm/{symbol}", None),
    ]))


def _fetch_key_metrics_ttm(ticker: str) -> Optional[dict]:
    symbol = ticker.upper()
    return _first(_get_json_any([
        (f"{STABLE_BASE_URL}/key-metrics-ttm", {"symbol": symbol}),
        (f"{LEGACY_BASE_URL}/key-metrics-ttm/{symbol}", None),
    ]))


def _field_history(items: list, *keys: str, absolute: bool = False, flip_sign: bool = False) -> list:
    values = []
    for item in items:
        value = _num(item, *keys)
        if value is None:
            value = 0.0
        if absolute:
            value = abs(value)
        if flip_sign:
            value = -value
        values.append(float(value))
    return values


def _debt_history(balance_sheets: list) -> list:
    history = []
    for bs in balance_sheets:
        debt = _num(bs, "totalDebt")
        if debt is None:
            debt = (_num(bs, "shortTermDebt") or 0.0) + (_num(bs, "longTermDebt") or 0.0)
        history.append(float(debt or 0.0))
    return history


def _cash_history(balance_sheets: list) -> list:
    return _field_history(
        balance_sheets,
        "cashAndCashEquivalents",
        "cashAndShortTermInvestments",
        "cashAndCashEquivalentsAndShortTermInvestments",
    )


def _current_shares(profile: Optional[dict], quote: Optional[dict], enterprise_values: list, income_statements: list) -> float:
    """Prefer current share count for today's fair value per share.

    This is where the prior model hurt AAPL: weighted-average diluted shares
    are correct for EPS, but today's DCF equity value should be divided by a
    current share count. FMP's marketCap/price or enterprise-value shares are
    better defaults for current valuation. If those are unavailable, fall back
    to latest diluted/basic average shares.
    """
    price = _num(quote, "price") or _num(profile, "price")
    market_cap = _num(quote, "marketCap") or _num(profile, "mktCap", "marketCap")
    if price and price > 0 and market_cap and market_cap > 0:
        return market_cap / price

    latest_ev = enterprise_values[-1] if enterprise_values else None
    shares = _num(latest_ev, "numberOfShares", "numberOfSharesOutstanding", "sharesOutstanding")
    if shares and shares > 0:
        return shares

    latest_income = income_statements[-1] if income_statements else None
    shares = _num(
        latest_income,
        "weightedAverageShsOutDil",
        "weightedAverageShsOut",
        "weightedAverageSharesDiluted",
        "weightedAverageSharesOutstanding",
    )
    return float(shares or 0.0)


def fetch_fmp_financial_snapshot(ticker: str, limit: int = 5) -> Optional[FinancialSnapshot]:
    """Build the app's FinancialSnapshot directly from FMP.

    Returns None when FMP is not configured or doesn't return enough statement
    history, allowing the caller to fall back to SEC/yfinance if desired.
    """
    if not is_configured():
        return None

    symbol = ticker.upper()
    profile = _fetch_profile(symbol)
    quote = _fetch_quote(symbol)
    income = _fetch_income_statements(symbol, limit)
    balance = _fetch_balance_sheets(symbol, limit)
    cash_flow = _fetch_cash_flows(symbol, limit)
    enterprise_values = _fetch_enterprise_values(symbol, limit)
    ratios_ttm = _fetch_ratios_ttm(symbol)
    key_metrics_ttm = _fetch_key_metrics_ttm(symbol)

    if len(income) < 2 or len(cash_flow) < 2:
        return None

    # Align all histories to the shortest available statement length. This is
    # safer than mixing a 5-year income statement with only 4 balance-sheet rows.
    n = min(len(income), len(cash_flow), len(balance) if balance else len(income))
    income = income[-n:]
    cash_flow = cash_flow[-n:]
    balance = balance[-n:] if balance else [{} for _ in range(n)]

    revenue_history = _field_history(income, "revenue")
    ebit_history = _field_history(income, "operatingIncome", "ebit")
    pretax_income_history = _field_history(income, "incomeBeforeTax", "incomeBeforeTaxRatio")
    # FMP incomeTaxExpense is normally a positive expense. The DCF default tax
    # rate divides tax expense by pre-tax income, so use a positive amount.
    tax_paid_history = _field_history(income, "incomeTaxExpense", "taxProvision", absolute=True)
    da_history = _field_history(cash_flow, "depreciationAndAmortization", "depreciationAndAmortizationExpense")
    capex_history = _field_history(cash_flow, "capitalExpenditure", "capitalExpenditures", absolute=True)
    # FMP's changeInWorkingCapital is a cash-flow-statement effect. Positive
    # means source of cash. The DCF formula wants ΔNWC where positive means use
    # of cash, so flip it.
    nwc_change_history = _field_history(cash_flow, "changeInWorkingCapital", flip_sign=True)
    interest_expense_history = _field_history(income, "interestExpense", absolute=True)
    total_debt_history = _debt_history(balance)
    cash_and_equivalents_history = _cash_history(balance)

    latest_balance = balance[-1] if balance else {}
    total_debt = total_debt_history[-1] if total_debt_history else 0.0
    cash_and_equivalents = cash_and_equivalents_history[-1] if cash_and_equivalents_history else 0.0
    if not cash_and_equivalents:
        cash_and_equivalents = _num(latest_balance, "cashAndCashEquivalents", "cashAndShortTermInvestments") or 0.0

    current_price = _num(quote, "price") or _num(profile, "price") or 0.0
    shares_outstanding = _current_shares(profile, quote, enterprise_values, income)

    trailing_pe = _num(quote, "pe") or _num(profile, "pe")
    ev_to_ebitda = _num(key_metrics_ttm, "enterpriseValueOverEBITDATTM", "evToEBITDATTM") or _num(
        ratios_ttm, "enterpriseValueMultipleTTM"
    )
    price_to_sales = _num(ratios_ttm, "priceToSalesRatioTTM") or _num(
        key_metrics_ttm, "priceToSalesRatioTTM"
    )
    trailing_eps = _num(quote, "eps") or _num(profile, "eps") or _num(
        income[-1], "epsdiluted", "eps"
    )

    warnings = []
    if not current_price:
        warnings.append("FMP did not return a current price for this ticker.")
    if not shares_outstanding:
        warnings.append("FMP did not return a usable current share count for this ticker.")
    if not any(total_debt_history):
        warnings.append("FMP did not return usable total-debt history; WACC debt weight may be understated.")

    years = []
    period_end_dates = []
    for stmt in income:
        date = _str(stmt, "date", "calendarYear") or ""
        period_end_dates.append(date)
        try:
            years.append(int(str(date)[:4]))
        except Exception:
            years.append(None)

    return FinancialSnapshot(
        ticker=symbol,
        company_name=_str(profile, "companyName", "companyNameLong") or symbol,
        sector=_str(profile, "sector"),
        industry=_str(profile, "industry"),
        currency=_str(profile, "currency") or _str(quote, "currency") or "USD",
        current_price=float(current_price or 0.0),
        shares_outstanding=float(shares_outstanding or 0.0),
        beta=_num(profile, "beta"),
        total_debt=float(total_debt or 0.0),
        cash_and_equivalents=float(cash_and_equivalents or 0.0),
        revenue_history=revenue_history,
        ebit_history=ebit_history,
        tax_paid_history=tax_paid_history,
        pretax_income_history=pretax_income_history,
        da_history=da_history,
        capex_history=capex_history,
        nwc_change_history=nwc_change_history,
        interest_expense_history=interest_expense_history,
        years=years,
        period_end_dates=period_end_dates,
        total_debt_history=total_debt_history,
        cash_and_equivalents_history=cash_and_equivalents_history,
        trailing_pe=trailing_pe,
        ev_to_ebitda=ev_to_ebitda,
        price_to_sales=price_to_sales,
        trailing_eps=trailing_eps,
        financial_currency=_str(profile, "currency") or _str(quote, "currency") or "USD",
        currency_mismatch_unresolved=False,
        data_source="Financial Modeling Prep",
        data_warnings=warnings,
    )


def debug_fmp_snapshot_status(ticker: str) -> dict:
    """Small diagnostic payload for /api/debug/fmp/{ticker}."""
    symbol = ticker.upper()
    if not is_configured():
        return {"configured": False, "symbol": symbol, "ok": False, "error": "FMP_API_KEY is not loaded."}

    profile = _fetch_profile(symbol)
    quote = _fetch_quote(symbol)
    income = _fetch_income_statements(symbol, 5)
    balance = _fetch_balance_sheets(symbol, 5)
    cash_flow = _fetch_cash_flows(symbol, 5)
    ok = len(income) >= 2 and len(cash_flow) >= 2
    return {
        "configured": True,
        "symbol": symbol,
        "ok": ok,
        "profile_found": bool(profile),
        "quote_found": bool(quote),
        "income_rows": len(income),
        "balance_rows": len(balance),
        "cash_flow_rows": len(cash_flow),
        "latest_error": latest_error(),
    }


def _price_history_rows(data) -> list:
    """Normalize FMP historical-price responses across old and stable endpoints."""
    if isinstance(data, dict):
        rows = data.get("historical") or data.get("data") or data.get("results")
        return rows if isinstance(rows, list) else []
    if isinstance(data, list):
        return data
    return []


def fetch_fmp_price_history(ticker: str, years: int = 5) -> Optional[list]:
    if not is_configured():
        return None
    end = datetime.utcnow().date()
    start = end - timedelta(days=years * 365 + 10)
    symbol = ticker.upper()

    # FMP has moved many endpoints from legacy /api/v3 to /stable. Try the
    # stable historical EOD shapes first, then the legacy endpoint.
    data = _get_json_any([
        (f"{STABLE_BASE_URL}/historical-price-eod/full", {"symbol": symbol, "from": start.isoformat(), "to": end.isoformat()}),
        (f"{STABLE_BASE_URL}/historical-price-eod", {"symbol": symbol, "from": start.isoformat(), "to": end.isoformat(), "limit": years * 366}),
        (f"{LEGACY_BASE_URL}/historical-price-full/{symbol}", {"from": start.isoformat(), "to": end.isoformat()}),
    ])
    rows = _price_history_rows(data)
    if not rows:
        return None

    # FMP usually returns newest -> oldest. Frontend expects oldest -> newest
    # and a reasonably compact series, so keep about weekly observations.
    rows = [r for r in rows if isinstance(r, dict)]
    rows = sorted(rows, key=lambda row: row.get("date") or row.get("calendarDate") or "")

    sampled = []
    last_date = None
    for item in rows:
        date = item.get("date") or item.get("calendarDate")
        close = _num(item, "adjClose", "adjClosePrice", "close", "price")
        if not date or close is None:
            continue
        try:
            current_date = datetime.fromisoformat(str(date)[:10]).date()
        except Exception:
            continue
        if last_date is None or (current_date - last_date).days >= 6:
            sampled.append({"date": current_date.isoformat(), "close": float(close)})
            last_date = current_date
    return sampled


def fetch_fmp_price_on_date(ticker: str, date_str: str) -> Optional[float]:
    if not is_configured() or not date_str:
        return None
    try:
        start = datetime.fromisoformat(date_str[:10]).date()
    except Exception:
        return None
    end = start + timedelta(days=7)
    symbol = ticker.upper()
    data = _get_json_any([
        (f"{STABLE_BASE_URL}/historical-price-eod/full", {"symbol": symbol, "from": start.isoformat(), "to": end.isoformat()}),
        (f"{STABLE_BASE_URL}/historical-price-eod", {"symbol": symbol, "from": start.isoformat(), "to": end.isoformat(), "limit": 10}),
        (f"{LEGACY_BASE_URL}/historical-price-full/{symbol}", {"from": start.isoformat(), "to": end.isoformat()}),
    ])
    rows = _price_history_rows(data)
    if not rows:
        return None
    rows = sorted([r for r in rows if isinstance(r, dict)], key=lambda row: row.get("date") or row.get("calendarDate") or "")
    for row in rows:
        price = _num(row, "adjClose", "adjClosePrice", "close", "price")
        if price is not None:
            return price
    return None


def fetch_fmp_latest_income_statement(ticker: str) -> Optional[dict]:
    data = _get_json(
        f"{LEGACY_BASE_URL}/income-statement/{ticker}",
        {"limit": 1},
    )
    if not data or not isinstance(data, list):
        return None
    return data[0]


def cross_check_against_fmp(ticker: str, revenue_latest: float, ebit_latest: float) -> Optional[str]:
    """Returns a warning string if FMP's most recent revenue or operating
    income disagrees with the app's source by more than the threshold, or None
    if they agree, FMP has no data, or the cross-check isn't configured."""
    if not is_configured():
        return None

    statement = fetch_fmp_latest_income_statement(ticker)
    if not statement:
        return None

    fmp_revenue = statement.get("revenue")
    fmp_ebit = statement.get("operatingIncome")

    disagreements = []
    if fmp_revenue and revenue_latest:
        gap = abs(fmp_revenue - revenue_latest) / revenue_latest
        if gap > DISAGREEMENT_THRESHOLD:
            disagreements.append(f"revenue ({gap * 100:.0f}% apart)")
    if fmp_ebit and ebit_latest:
        gap = abs(fmp_ebit - ebit_latest) / ebit_latest
        if gap > DISAGREEMENT_THRESHOLD:
            disagreements.append(f"operating income ({gap * 100:.0f}% apart)")

    if not disagreements:
        return None

    return (
        f"Financial Modeling Prep reports a different most-recent-year {' and '.join(disagreements)} "
        "than the app's primary source does for this ticker. When two independent sources disagree this much, "
        "treat the underlying figures with extra caution."
    )


def _normalise_fmp_dcf_item(item: dict) -> Optional[dict]:
    """Return a small, frontend-safe record from FMP's DCF endpoints.

    FMP has changed field casing across old/new endpoints, so this accepts a
    few variants rather than assuming only one exact JSON shape.
    """
    if not isinstance(item, dict):
        return None

    dcf = item.get("dcf") or item.get("DCF")
    price = item.get("Stock Price") or item.get("stockPrice") or item.get("stock_price")
    date = item.get("date") or item.get("Date")

    try:
        dcf_value = float(dcf) if dcf is not None else None
    except (TypeError, ValueError):
        dcf_value = None

    try:
        price_value = float(price) if price is not None else None
    except (TypeError, ValueError):
        price_value = None

    if dcf_value is None and price_value is None:
        return None

    return {
        "date": date,
        "dcf": dcf_value,
        "stock_price": price_value,
    }


def fetch_fmp_dcf_valuation(ticker: str) -> Optional[dict]:
    """Fetch FMP's standard prebuilt DCF valuation.

    Endpoint observed in FMP's current API viewer:
        /stable/discounted-cash-flow?symbol=AAPL
    """
    data = _get_json(
        f"{STABLE_BASE_URL}/discounted-cash-flow",
        {"symbol": ticker.upper()},
    )
    if not data or not isinstance(data, list):
        return None
    return _normalise_fmp_dcf_item(data[0])


def fetch_fmp_levered_dcf_valuation(ticker: str) -> Optional[dict]:
    """Fetch FMP's prebuilt levered DCF valuation.

    Endpoint observed in FMP's current API viewer:
        /stable/levered-discounted-cash-flow?symbol=AAPL
    """
    data = _get_json(
        f"{STABLE_BASE_URL}/levered-discounted-cash-flow",
        {"symbol": ticker.upper()},
    )
    if not data or not isinstance(data, list):
        return None
    return _normalise_fmp_dcf_item(data[0])


def fetch_fmp_dcf_benchmarks(ticker: str) -> dict:
    """Return optional FMP DCF benchmarks without throwing.

    The response always has a stable shape so the frontend can show either
    real benchmark numbers or a helpful "not configured" message.
    """
    if not is_configured():
        return {
            "configured": False,
            "discounted_cash_flow": None,
            "levered_dcf": None,
            "source": "Financial Modeling Prep",
        }

    return {
        "configured": True,
        "discounted_cash_flow": fetch_fmp_dcf_valuation(ticker),
        "levered_dcf": fetch_fmp_levered_dcf_valuation(ticker),
        "source": "Financial Modeling Prep",
    }
