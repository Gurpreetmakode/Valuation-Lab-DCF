"""
Peer comparison for sanity-checking a DCF against how the market actually
prices similar companies. Peer lists are a small, static set of large,
liquid names per GICS sector (as reported by yfinance's `sector` field),
not a scraped or paid dataset, so this is a rough benchmark, not a precise
sector index.
"""

import yfinance as yf

SECTOR_PEERS = {
    "Technology": ["AAPL", "MSFT", "GOOGL", "ORCL", "ADBE"],
    "Financial Services": ["JPM", "BAC", "WFC", "MA", "V"],
    "Healthcare": ["JNJ", "UNH", "PFE", "ABBV", "MRK"],
    "Consumer Cyclical": ["AMZN", "TSLA", "HD", "MCD", "NKE"],
    "Consumer Defensive": ["PG", "KO", "PEP", "WMT", "COST"],
    "Energy": ["XOM", "CVX", "COP", "SLB", "EOG"],
    "Industrials": ["HON", "UNP", "CAT", "GE", "BA"],
    "Utilities": ["NEE", "DUK", "SO", "D", "AEP"],
    "Real Estate": ["PLD", "AMT", "EQIX", "PSA", "O"],
    "Communication Services": ["GOOG", "META", "NFLX", "DIS", "CMCSA"],
    "Basic Materials": ["LIN", "SHW", "APD", "FCX", "NEM"],
}


def fetch_peer_average_pe(sector: str, exclude_ticker: str) -> dict:
    """Average trailing P/E across a small static peer set for the given
    sector, excluding the ticker being valued. Returns a dict with the
    average and how many peers actually had usable data, since some
    tickers report no trailing P/E (loss-making peers, for example)."""
    peers = SECTOR_PEERS.get(sector, [])
    peers = [p for p in peers if p.upper() != exclude_ticker.upper()]

    pe_values = []
    for peer in peers:
        try:
            info = yf.Ticker(peer).info or {}
            pe = info.get("trailingPE")
            if pe and pe > 0:
                pe_values.append(pe)
        except Exception:
            continue

    if not pe_values:
        return {"average_pe": None, "peers_used": 0, "peers_considered": len(peers)}

    return {
        "average_pe": sum(pe_values) / len(pe_values),
        "peers_used": len(pe_values),
        "peers_considered": len(peers),
    }
