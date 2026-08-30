"""
Autocomplete for the search box. Yahoo Finance exposes a free, public
search endpoint that yfinance itself does not wrap, so this calls it
directly. It is best-effort: any failure (network, rate limiting, an
unexpected response shape) just returns an empty list rather than raising,
since a broken autocomplete should never block a plain ticker search.
"""

import requests

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; IntrinsicValuationApp/1.0)"}
_SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"


def search_tickers(query: str, limit: int = 8) -> list:
    query = (query or "").strip()
    if not query:
        return []

    try:
        response = requests.get(
            _SEARCH_URL,
            params={"q": query, "quotesCount": limit, "newsCount": 0, "listsCount": 0},
            headers=_HEADERS,
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []

    results = []
    for quote in data.get("quotes", []):
        symbol = quote.get("symbol")
        name = quote.get("longname") or quote.get("shortname")
        if not symbol or not name:
            continue
        results.append(
            {
                "symbol": symbol,
                "name": name,
                "exchange": quote.get("exchDisp"),
                "type": quote.get("quoteType"),
            }
        )

    return results[:limit]
