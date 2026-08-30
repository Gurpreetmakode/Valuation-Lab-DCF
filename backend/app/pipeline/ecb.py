"""
Euro-area risk-free rate from the European Central Bank's free, keyless
Data Portal API, for EUR-denominated companies. Using the US 10-year
Treasury yield as "the" risk-free rate for every currency is conceptually
wrong; a Euro-area company's cost of equity should be built from a
Euro-area rate.

HONESTY NOTE FOR WHOEVER MAINTAINS THIS NEXT: the exact ECB series key
below (a 10-year AAA euro-area spot yield from the ECB's "YC" yield-curve
dataset) was not verified against a live call, since this environment
cannot reach the internet. If it 404s or the response shape doesn't match
what this code expects, that will simply trigger the fallback to the US
Treasury rate rather than break anything, but it is worth confirming the
series key against ECB's Data Portal documentation
(https://data.ecb.europa.eu) the first time this runs somewhere with real
network access, and adjusting SERIES_KEY below if needed.
"""

from typing import Optional

import requests

BASE_URL = "https://data-api.ecb.europa.eu/service/data"
FLOW_REF = "YC"
SERIES_KEY = "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y"  # 10Y AAA euro-area spot rate, verify live (see module docstring)


def fetch_ecb_10y_rate() -> Optional[float]:
    """Most recent 10-year euro-area risk-free rate as a decimal (e.g.
    0.028 for 2.8%). Returns None if the series can't be fetched or parsed,
    so callers can fall back to a different rate rather than fail."""
    try:
        url = f"{BASE_URL}/{FLOW_REF}/{SERIES_KEY}"
        response = requests.get(url, headers={"Accept": "application/json"}, params={"lastNObservations": 1}, timeout=10)
        response.raise_for_status()
        data = response.json()

        series = data["dataSets"][0]["series"]
        first_series = next(iter(series.values()))
        observations = first_series["observations"]
        last_obs = next(iter(observations.values()))
        value = last_obs[0]
        return float(value) / 100.0
    except Exception:
        return None
