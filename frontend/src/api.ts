import type { Assumptions, DcfView, PriceHistoryResponse, SearchResponse, ValuationResponse } from './types';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

export async function fetchValuation(
  ticker: string,
  overrides?: Partial<Assumptions>,
  dcfView: DcfView = 'fmp'
): Promise<ValuationResponse> {
  const params = new URLSearchParams();
  params.set('dcf_view', dcfView);
  if (overrides) {
    for (const [key, value] of Object.entries(overrides)) {
      if (value !== undefined && value !== null) {
        params.set(key, String(value));
      }
    }
  }

  const query = params.toString();
  const url = `${API_BASE}/api/valuation/${encodeURIComponent(ticker)}${query ? `?${query}` : ''}`;

  const response = await fetch(url);
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: 'Something went wrong fetching that ticker.' }));
    throw new Error(body.detail ?? `Request failed with status ${response.status}`);
  }
  return response.json();
}

export async function fetchPriceHistory(ticker: string, years = 5): Promise<PriceHistoryResponse> {
  const url = `${API_BASE}/api/price-history/${encodeURIComponent(ticker)}?years=${years}`;
  const response = await fetch(url);
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: 'Could not load price history.' }));
    throw new Error(body.detail ?? `Request failed with status ${response.status}`);
  }
  return response.json();
}

export async function searchTickers(query: string): Promise<SearchResponse> {
  const url = `${API_BASE}/api/search?q=${encodeURIComponent(query)}`;
  const response = await fetch(url);
  if (!response.ok) {
    return { query, results: [] };
  }
  return response.json();
}
