import { useEffect, useRef, useState } from 'react';
import './App.css';
import { fetchPriceHistory, fetchValuation, searchTickers } from './api';
import { AssumptionsPanel } from './components/AssumptionsPanel';
import { BacktestPanel } from './components/BacktestPanel';
import { CaveatBanner } from './components/CaveatBanner';
import { EmptyState } from './components/EmptyState';
import { FCFEChart } from './components/FCFEChart';
import { HowItWorks } from './components/HowItWorks';
import { Masthead } from './components/Masthead';
import { MultiplesPanel } from './components/MultiplesPanel';
import { PriceHistoryChart } from './components/PriceHistoryChart';
import { SensitivityGrid } from './components/SensitivityGrid';
import { ValuationLine } from './components/ValuationLine';
import { WatchlistPanel } from './components/WatchlistPanel';
import { currencySymbol } from './currency';
import type {
  Assumptions,
  DcfScenario,
  DcfView,
  EditableAssumptionField,
  OverrideFlags,
  PricePoint,
  TickerSuggestion,
  ValuationResponse,
  WatchlistEntry,
} from './types';
import { loadWatchlist, removeWatchlistEntry, saveWatchlist, upsertWatchlistEntry } from './watchlist';

const EMPTY_OVERRIDES: Partial<Assumptions> = {};

const EDITABLE_FIELDS: EditableAssumptionField[] = [
  'growth_rate',
  'discount_rate',
  'risk_free_rate',
  'beta',
  'equity_risk_premium',
  'cost_of_debt',
  'debt_weight',
  'ebit_margin',
  'tax_rate',
  'da_pct',
  'capex_pct',
  'nwc_pct',
  'terminal_growth',
];

function cleanTicker(value: string) {
  return value.trim().toUpperCase();
}

function looksLikeTicker(value: string) {
  const trimmed = value.trim().toUpperCase();
  // Common ticker forms: AAPL, GOOG, CARL-B.CO, NOVO-B.CO.
  return /^[A-Z0-9][A-Z0-9.\-]{0,14}$/.test(trimmed);
}

function serialiseOverrides(overrides?: Partial<Assumptions>) {
  return JSON.stringify(
    Object.entries(overrides ?? {})
      .filter(([, value]) => value !== undefined && value !== null)
      .sort(([a], [b]) => a.localeCompare(b))
  );
}

function valuationCacheKey(ticker: string, view: DcfView, overrides?: Partial<Assumptions>) {
  return `${cleanTicker(ticker)}::${view}::${serialiseOverrides(overrides)}`;
}

function flagsFromOverrides(overrides: Partial<Assumptions>): OverrideFlags {
  const flags = {} as OverrideFlags;
  for (const field of EDITABLE_FIELDS) {
    flags[field] = Object.prototype.hasOwnProperty.call(overrides, field);
  }
  return flags;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function ensureDiscountSpread(discountRate: number, terminalGrowth: number, minSpread = 0.035) {
  return Math.max(discountRate, terminalGrowth + minSpread);
}

function scenarioOverrides(scenario: DcfScenario, defaults: Assumptions): Partial<Assumptions> {
  if (scenario === 'conservative') {
    // Conservative is the raw/free-data model default. This keeps the current
    // strict Yahoo result visible, but labels it correctly as conservative.
    return {};
  }

  if (scenario === 'neutral') {
    const growth = clamp(Math.max(defaults.growth_rate + 0.015, 0.035), -0.02, 0.075);
    const terminalGrowth = clamp(Math.max(defaults.terminal_growth, 0.025), 0.0, 0.03);
    const discount = ensureDiscountSpread(clamp(defaults.discount_rate - 0.02, 0.065, 0.105), terminalGrowth);
    return {
      growth_rate: growth,
      discount_rate: discount,
      terminal_growth: terminalGrowth,
    };
  }

  if (scenario === 'bullish') {
    const growth = clamp(Math.max(defaults.growth_rate + 0.035, 0.055), -0.01, 0.12);
    const terminalGrowth = clamp(Math.max(defaults.terminal_growth + 0.0025, 0.0275), 0.0, 0.0325);
    const discount = ensureDiscountSpread(clamp(defaults.discount_rate - 0.035, 0.055, 0.095), terminalGrowth, 0.03);
    return {
      growth_rate: growth,
      discount_rate: discount,
      terminal_growth: terminalGrowth,
    };
  }

  return {};
}

function App() {
  const [ticker, setTicker] = useState<string | null>(null);
  const [data, setData] = useState<ValuationResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [priceHistory, setPriceHistory] = useState<PricePoint[]>([]);
  const [priceHistoryLoading, setPriceHistoryLoading] = useState(false);
  const [priceHistoryError, setPriceHistoryError] = useState<string | null>(null);

  const [watchlist, setWatchlist] = useState<WatchlistEntry[]>([]);
  // Default to the free-data/internal model. FMP is fetched only after the
  // user explicitly opens the FMP DCF tab.
  const [activeDcfView, setActiveDcfView] = useState<DcfView>('yfinance');
  const [scenarioByView, setScenarioByView] = useState<Record<DcfView, DcfScenario>>(
    { fmp: 'conservative', yfinance: 'conservative' }
  );
  const [draftOverridesByView, setDraftOverridesByView] = useState<Record<DcfView, Partial<Assumptions>>>(
    { fmp: {}, yfinance: {} }
  );
  const [lastAppliedOverridesByView, setLastAppliedOverridesByView] = useState<Record<DcfView, Partial<Assumptions>>>(
    { fmp: {}, yfinance: {} }
  );
  const [lastAppliedScenarioByView, setLastAppliedScenarioByView] = useState<Record<DcfView, DcfScenario>>(
    { fmp: 'conservative', yfinance: 'conservative' }
  );
  const [searchChoices, setSearchChoices] = useState<TickerSuggestion[]>([]);
  const [searchChoiceQuery, setSearchChoiceQuery] = useState('');

  const valuationCache = useRef<Map<string, ValuationResponse>>(new Map());
  const priceHistoryCache = useRef<Map<string, PricePoint[]>>(new Map());

  useEffect(() => {
    setWatchlist(loadWatchlist());
  }, []);

  async function loadValuation(
    tickerToLoad: string,
    view: DcfView,
    overrides: Partial<Assumptions> = EMPTY_OVERRIDES,
    useCache = true
  ) {
    const normalisedTicker = cleanTicker(tickerToLoad);
    const cacheKey = valuationCacheKey(normalisedTicker, view, overrides);
    const cached = valuationCache.current.get(cacheKey);
    if (useCache && cached) {
      setData(cached);
      setLastAppliedOverridesByView((prev) => ({ ...prev, [view]: overrides }));
      setLastAppliedScenarioByView((prev) => ({ ...prev, [view]: scenarioByView[view] }));
      return cached;
    }

    setIsLoading(true);
    setError(null);
    try {
      const result = await fetchValuation(normalisedTicker, overrides, view);
      valuationCache.current.set(cacheKey, result);
      setData(result);
      setLastAppliedOverridesByView((prev) => ({ ...prev, [view]: overrides }));
      setLastAppliedScenarioByView((prev) => ({ ...prev, [view]: scenarioByView[view] }));
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
      setData(null);
      return null;
    } finally {
      setIsLoading(false);
    }
  }

  async function resolveTickerOrShowChoices(rawQuery: string) {
    const query = rawQuery.trim();
    if (!query) return null;

    // If the user typed a company name such as "apple", do not blindly convert
    // it to APPLE and fail. Ask Yahoo's symbol search and show clickable choices.
    const suggestions = await searchTickers(query);
    const upper = query.toUpperCase();
    const exact = suggestions.results.find((s) => s.symbol.toUpperCase() === upper);

    if (exact) {
      return exact.symbol.toUpperCase();
    }

    if (suggestions.results.length > 0 && (!looksLikeTicker(query) || suggestions.results[0].symbol.toUpperCase() !== upper)) {
      setSearchChoices(suggestions.results);
      setSearchChoiceQuery(query);
      setError(null);
      setData(null);
      return null;
    }

    return upper;
  }

  async function runSearch(rawTicker: string) {
    const resolvedTicker = await resolveTickerOrShowChoices(rawTicker);
    if (!resolvedTicker) return;

    setSearchChoices([]);
    setSearchChoiceQuery('');
    setTicker(resolvedTicker);

    // A fresh search always opens Yahoo/Internal DCF first. This avoids wasting
    // FMP calls while users are trying many tickers in the free tab.
    setActiveDcfView('yfinance');
    setScenarioByView({ fmp: 'conservative', yfinance: 'conservative' });
    setDraftOverridesByView({ fmp: {}, yfinance: {} });
    setLastAppliedOverridesByView({ fmp: {}, yfinance: {} });
    setLastAppliedScenarioByView({ fmp: 'conservative', yfinance: 'conservative' });

    await loadValuation(resolvedTicker, 'yfinance', EMPTY_OVERRIDES, true);
    loadHistory(resolvedTicker);
  }

  async function loadHistory(tickerToLoad: string) {
    const normalisedTicker = cleanTicker(tickerToLoad);
    const cached = priceHistoryCache.current.get(normalisedTicker);
    if (cached) {
      setPriceHistory(cached);
      setPriceHistoryError(null);
      return;
    }

    setPriceHistoryLoading(true);
    setPriceHistoryError(null);
    try {
      const result = await fetchPriceHistory(normalisedTicker);
      priceHistoryCache.current.set(normalisedTicker, result.history);
      setPriceHistory(result.history);
    } catch (err) {
      setPriceHistoryError(err instanceof Error ? err.message : 'Could not load price history.');
      setPriceHistory([]);
    } finally {
      setPriceHistoryLoading(false);
    }
  }

  async function handleDcfViewChange(view: DcfView) {
    if (view === activeDcfView) return;
    setActiveDcfView(view);

    if (!ticker) return;

    // Do not use staged-but-uncalculated edits when switching tabs. Show the
    // last calculated version of that tab from memory, and only fetch if that
    // tab has never been loaded before for this ticker. Opening FMP is the only
    // action that can spend an FMP call; Yahoo searches never prewarm FMP.
    const appliedOverrides = lastAppliedOverridesByView[view] ?? EMPTY_OVERRIDES;
    await loadValuation(ticker, view, appliedOverrides, true);
  }

  function handleAssumptionChange(field: EditableAssumptionField, value: number) {
    setScenarioByView((prev) => ({ ...prev, [activeDcfView]: 'custom' }));
    setDraftOverridesByView((prev) => ({
      ...prev,
      [activeDcfView]: { ...prev[activeDcfView], [field]: value },
    }));
  }

  function handleResetAssumption(field: EditableAssumptionField) {
    setScenarioByView((prev) => ({ ...prev, [activeDcfView]: 'custom' }));
    setDraftOverridesByView((prev) => {
      const nextForView = { ...prev[activeDcfView] };
      delete nextForView[field];
      return { ...prev, [activeDcfView]: nextForView };
    });
  }

  function handleScenarioChange(scenario: DcfScenario) {
    setScenarioByView((prev) => ({ ...prev, [activeDcfView]: scenario }));
    if (!data) return;
    if (scenario === 'custom') return;
    const preset = scenarioOverrides(scenario, data.default_assumptions);
    setDraftOverridesByView((prev) => ({ ...prev, [activeDcfView]: preset }));
  }

  function handleResetAllAssumptions() {
    setScenarioByView((prev) => ({ ...prev, [activeDcfView]: 'conservative' }));
    setDraftOverridesByView((prev) => ({ ...prev, [activeDcfView]: {} }));

    // Resetting the UI back to default should not spend an FMP call. If the
    // default valuation for this tab/ticker has already been loaded, restore it
    // from the in-memory cache immediately.
    if (!ticker) return;
    const defaultKey = valuationCacheKey(ticker, activeDcfView, EMPTY_OVERRIDES);
    const cachedDefault = valuationCache.current.get(defaultKey);
    if (cachedDefault) {
      setData(cachedDefault);
      setLastAppliedOverridesByView((prev) => ({ ...prev, [activeDcfView]: {} }));
      setLastAppliedScenarioByView((prev) => ({ ...prev, [activeDcfView]: 'conservative' }));
    }
  }

  async function handleCalculateAssumptions() {
    if (!ticker) return;
    const overrides = draftOverridesByView[activeDcfView] ?? EMPTY_OVERRIDES;
    await loadValuation(ticker, activeDcfView, overrides, true);
  }

  function handleAddToWatchlist() {
    if (!data) return;
    const entry: WatchlistEntry = {
      ticker: data.ticker,
      companyName: data.company_name,
      fairValue: data.valuation.fair_value_per_share,
      currentPrice: data.valuation.current_price,
      gapPercent: data.valuation.gap_percent,
      verdict: data.valuation.verdict,
      currency: data.currency,
      savedAt: new Date().toISOString(),
    };
    const updated = upsertWatchlistEntry(watchlist, entry);
    setWatchlist(updated);
    saveWatchlist(updated);
  }

  function handleRemoveFromWatchlist(tickerToRemove: string) {
    const updated = removeWatchlistEntry(watchlist, tickerToRemove);
    setWatchlist(updated);
    saveWatchlist(updated);
  }

  const activeDraftOverrides = draftOverridesByView[activeDcfView] ?? EMPTY_OVERRIDES;
  const activeAppliedOverrides = lastAppliedOverridesByView[activeDcfView] ?? EMPTY_OVERRIDES;
  const activeScenario = scenarioByView[activeDcfView];
  const activeAppliedScenario = lastAppliedScenarioByView[activeDcfView];
  const displayValues: Assumptions | null = data
    ? { ...(data.default_assumptions ?? data.assumptions), ...activeDraftOverrides }
    : null;
  const draftFlags = flagsFromOverrides(activeDraftOverrides);
  const hasPendingChanges =
    serialiseOverrides(activeDraftOverrides) !== serialiseOverrides(activeAppliedOverrides) || activeScenario !== activeAppliedScenario;

  return (
    <div className="app">
      <Masthead onSearch={runSearch} isLoading={isLoading} />

      <main className="app__main">
        {!data && !error && searchChoices.length === 0 && <EmptyState />}

        {searchChoices.length > 0 && (
          <section className="app__choices" aria-label="Choose ticker">
            <h2>Which ticker did you mean?</h2>
            <p>
              “{searchChoiceQuery}” could refer to several securities. Choose one to build the DCF.
            </p>
            <div className="app__choice-grid">
              {searchChoices.map((choice) => (
                <button
                  type="button"
                  className="app__choice-card"
                  key={`${choice.symbol}-${choice.exchange ?? ''}`}
                  onClick={() => runSearch(choice.symbol)}
                >
                  <span className="mono app__choice-symbol">{choice.symbol}</span>
                  <span className="app__choice-name">{choice.name}</span>
                  <span className="app__choice-meta">
                    {[choice.exchange, choice.type].filter(Boolean).join(' · ')}
                  </span>
                </button>
              ))}
            </div>
          </section>
        )}

        {error && (
          <div className="app__error">
            <p>{error}</p>
          </div>
        )}

        {data && displayValues && (
          <>
            <div className="app__heading">
              <h2 className="app__company">{data.company_name}</h2>
              <span className="mono app__ticker">{data.ticker}</span>
              {data.sector && <span className="app__sector">{data.sector}</span>}
              <span className="app__data-source" title="Which source this ticker's financial statements came from">
                {data.data_source}
              </span>
              {isLoading && <span className="app__recalculating">calculating…</span>}
            </div>

            <CaveatBanner reasons={data.suitability.reasons} warnings={data.data_warnings} />

            <div className="app__dcf-tabs" role="tablist" aria-label="DCF model source">
              <button
                type="button"
                role="tab"
                aria-selected={activeDcfView === 'yfinance'}
                className={`app__dcf-tab ${activeDcfView === 'yfinance' ? 'app__dcf-tab--active' : ''}`}
                onClick={() => handleDcfViewChange('yfinance')}
              >
                Yahoo / Internal DCF
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeDcfView === 'fmp'}
                className={`app__dcf-tab ${activeDcfView === 'fmp' ? 'app__dcf-tab--active' : ''}`}
                onClick={() => handleDcfViewChange('fmp')}
              >
                FMP DCF
              </button>
            </div>

            <div className={`app__content ${isLoading ? 'app__content--loading' : ''}`}>
              <div className="app__tab-note">
                {activeDcfView === 'fmp' ? (
                  <>
                    <strong>FMP DCF tab:</strong> this tab fetches Financial Modeling Prep only after you open it.
                    The headline fair value comes from FMP's prebuilt DCF endpoint. Scenario/custom assumptions
                    recalculate the app's internal FCFF model using cached base data, not fresh FMP calls.
                  </>
                ) : (
                  <>
                    <strong>Yahoo / Internal DCF tab:</strong> this is the default free-data model. You can search
                    as many tickers as you want here without preloading FMP data. FMP is only touched if you open
                    the FMP DCF tab.
                  </>
                )}
              </div>

              <AssumptionsPanel
  values={displayValues}
  overrides={draftFlags}
  scenario={activeScenario}
  onScenarioChange={handleScenarioChange}
  onChange={handleAssumptionChange}
  onResetField={handleResetAssumption}
  onResetAll={handleResetAllAssumptions}
  onCalculate={handleCalculateAssumptions}
  isCalculating={isLoading}
  hasPendingChanges={hasPendingChanges}
  modeLabel={activeDcfView === 'fmp' ? 'FMP DCF tab' : 'Yahoo/Internal DCF tab'}
  showScenarioSelector={activeDcfView !== 'fmp'}
/>

              <FCFEChart
                projection={data.projection}
                companyName={data.company_name}
                currency={currencySymbol(data.currency)}
              />

              <ValuationLine
                valuation={data.valuation}
                reliability={data.reliability}
                currency={currencySymbol(data.currency)}
              />

              <PriceHistoryChart
                history={priceHistory}
                fairValue={data.valuation.fair_value_per_share}
                currency={currencySymbol(data.currency)}
                isLoading={priceHistoryLoading}
                error={priceHistoryError}
              />

              <MultiplesPanel
                multiples={data.multiples}
                fmpBenchmark={data.fmp_benchmark}
                currency={currencySymbol(data.currency)}
              />

              {activeDcfView === 'yfinance' && (
                <>
                  <BacktestPanel backtest={data.backtest} currency={currencySymbol(data.currency)} />
                  <SensitivityGrid
                    grid={data.sensitivity}
                    currentPrice={data.valuation.current_price}
                    currency={currencySymbol(data.currency)}
                  />
                </>
              )}

              <WatchlistPanel
                entries={watchlist}
                currentTicker={data.ticker}
                onAdd={handleAddToWatchlist}
                onRemove={handleRemoveFromWatchlist}
                onSelect={runSearch}
              />
              <HowItWorks />
            </div>
          </>
        )}
      </main>

      <footer className="app__footer">
        <p>
          Built with free market data. Not investment advice.
        </p>
      </footer>
    </div>
  );
}

export default App;
