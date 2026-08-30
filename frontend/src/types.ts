export interface Suitability {
  suitable: boolean;
  reasons: string[];
}

export interface Assumptions {
  growth_rate: number;
  discount_rate: number;
  risk_free_rate: number;
  beta: number;
  equity_risk_premium: number;
  cost_of_debt: number;
  debt_weight: number;
  cost_of_equity: number;
  ebit_margin: number;
  tax_rate: number;
  da_pct: number;
  capex_pct: number;
  nwc_pct: number;
  terminal_growth: number;
}

export type AssumptionField = keyof Assumptions;

export interface OverrideFlags {
  growth_rate: boolean;
  discount_rate: boolean;
  risk_free_rate: boolean;
  beta: boolean;
  equity_risk_premium: boolean;
  cost_of_debt: boolean;
  debt_weight: boolean;
  ebit_margin: boolean;
  tax_rate: boolean;
  da_pct: boolean;
  capex_pct: boolean;
  nwc_pct: boolean;
  terminal_growth: boolean;
}

export type EditableAssumptionField = keyof OverrideFlags;

export interface ValuationSummary {
  fair_value_per_share: number;
  current_price: number;
  gap_percent: number;
  verdict: 'undervalued' | 'overvalued' | 'fairly valued';
}

export interface Projection {
  years: number[];
  projected_fcfe: number[];
  discounted_fcfe: number[];
  terminal_value_discounted: number;
  terminal_value_share: number;
}

export interface SensitivityGrid {
  growth_rates: number[];
  discount_rates: number[];
  values: (number | null)[][];
  current_cell: { row: number; col: number };
}

export interface FmpDcfItem {
  date: string | null;
  dcf: number | null;
  stock_price: number | null;
}

export interface FmpBenchmark {
  configured: boolean;
  discounted_cash_flow: FmpDcfItem | null;
  levered_dcf: FmpDcfItem | null;
  source: string;
  wacc_to_match_standard_dcf: number | null;
  wacc_to_match_levered_dcf: number | null;
}

export interface Multiples {
  trailing_pe: number | null;
  ev_to_ebitda: number | null;
  price_to_sales: number | null;
  dcf_implied_pe: number | null;
  sector_peer_average_pe: number | null;
  peer_data_points: number;
  implied_growth_rate: number | null;
  implied_discount_rate: number | null;
  your_growth_rate: number;
  your_discount_rate: number;
}

export interface BacktestCheckpoint {
  as_of_date: string;
  implied_fair_value_then: number;
  actual_price_then: number;
  price_change_pct: number;
  model_gap_then_pct: number;
  direction_correct: boolean;
}

export interface BacktestResult {
  available: boolean;
  reason: string | null;
  actual_price_now: number | null;
  correct_count: number;
  total_count: number;
  checkpoints: BacktestCheckpoint[];
}

export interface Reliability {
  confident: boolean;
  reason: string | null;
}

export type DcfView = 'fmp' | 'yfinance';
export type DcfScenario = 'conservative' | 'neutral' | 'bullish' | 'custom';

export interface ValuationResponse {
  ticker: string;
  company_name: string;
  sector: string | null;
  industry: string | null;
  currency: string;
  data_source: string;
  dcf_view: DcfView;
  suitability: Suitability;
  data_warnings: string[];
  default_assumptions: Assumptions;
  assumptions: Assumptions;
  overrides: OverrideFlags;
  valuation: ValuationSummary;
  reliability: Reliability;
  projection: Projection;
  sensitivity: SensitivityGrid;
  fmp_benchmark: FmpBenchmark;
  multiples: Multiples;
  backtest: BacktestResult;
}

export interface PricePoint {
  date: string;
  close: number;
}

export interface PriceHistoryResponse {
  ticker: string;
  history: PricePoint[];
}

export interface TickerSuggestion {
  symbol: string;
  name: string;
  exchange: string | null;
  type: string | null;
}

export interface SearchResponse {
  query: string;
  results: TickerSuggestion[];
}

export interface WatchlistEntry {
  ticker: string;
  companyName: string;
  fairValue: number;
  currentPrice: number;
  gapPercent: number;
  verdict: ValuationSummary['verdict'];
  currency: string;
  savedAt: string;
}

export interface ApiError {
  detail: string;
}
