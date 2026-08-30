"""
Picks a currency-appropriate risk-free rate. Using the US 10-year Treasury
yield for every company regardless of what currency it trades in is
conceptually wrong; a EUR/DKK company's cost of equity should be built
from a Euro-area rate. Falls back to the US Treasury rate for any
currency without a dedicated source, or if the dedicated source's fetch
fails, so a rate is always returned.
"""

from app.pipeline import ecb, yahoo


def fetch_risk_free_rate_for_currency(currency: str) -> float:
    if currency in {"EUR", "DKK"}:
        ecb_rate = ecb.fetch_ecb_10y_rate()
        if ecb_rate is not None:
            return ecb_rate
    return yahoo.fetch_risk_free_rate()
