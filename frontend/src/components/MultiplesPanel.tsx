import './MultiplesPanel.css';
import type { FmpBenchmark, Multiples } from '../types';

interface MultiplesPanelProps {
  multiples: Multiples;
  fmpBenchmark: FmpBenchmark;
  currency: string;
}

function Row({ label, value, suffix = '×' }: { label: string; value: number | null; suffix?: string }) {
  return (
    <div className="multiples__row">
      <span className="multiples__label">{label}</span>
      <span className="mono multiples__value">{value !== null ? `${value.toFixed(1)}${suffix}` : '—'}</span>
    </div>
  );
}

function MoneyRow({ label, value, currency }: { label: string; value: number | null | undefined; currency: string }) {
  return (
    <div className="multiples__row">
      <span className="multiples__label">{label}</span>
      <span className="mono multiples__value">
        {value !== null && value !== undefined ? `${currency}${value.toFixed(2)}` : '—'}
      </span>
    </div>
  );
}

function PercentRow({ label, value }: { label: string; value: number | null | undefined }) {
  return (
    <div className="multiples__row">
      <span className="multiples__label">{label}</span>
      <span className="mono multiples__value">
        {value !== null && value !== undefined ? `${(value * 100).toFixed(1)}%` : '—'}
      </span>
    </div>
  );
}

export function MultiplesPanel({ multiples, fmpBenchmark, currency }: MultiplesPanelProps) {
  const hasMismatch =
    multiples.dcf_implied_pe !== null &&
    multiples.trailing_pe !== null &&
    Math.abs(multiples.dcf_implied_pe - multiples.trailing_pe) / multiples.trailing_pe > 0.2;

  const impliedGrowthPct = multiples.implied_growth_rate !== null ? multiples.implied_growth_rate * 100 : null;
  const impliedDiscountPct = multiples.implied_discount_rate !== null ? multiples.implied_discount_rate * 100 : null;
  const yourGrowthPct = multiples.your_growth_rate * 100;
  const yourDiscountPct = multiples.your_discount_rate * 100;

  return (
    <div className="multiples">
      <h2 className="multiples__title">Multiples check</h2>
      <p className="multiples__subtitle">
        How this valuation compares to how the market actually prices this stock, its peers and an optional
        Financial Modeling Prep benchmark.
      </p>

      <div className="multiples__grid">
        <div>
          <p className="multiples__group-label">Current market multiples</p>
          <Row label="Trailing P/E" value={multiples.trailing_pe} />
          <Row label="EV / EBITDA" value={multiples.ev_to_ebitda} />
          <Row label="Price / Sales" value={multiples.price_to_sales} />
        </div>
        <div>
          <p className="multiples__group-label">This DCF implies</p>
          <Row label="Implied P/E" value={multiples.dcf_implied_pe} />
          <Row
            label={`Sector peer avg P/E${multiples.peer_data_points ? ` (${multiples.peer_data_points} peers)` : ''}`}
            value={multiples.sector_peer_average_pe}
          />
        </div>
      </div>

      <div className="multiples__fmp-benchmark">
        <p className="multiples__group-label">FMP benchmark</p>
        {fmpBenchmark.configured ? (
          <>
            <div className="multiples__grid">
              <div>
                <MoneyRow
                  label="FMP standard DCF"
                  value={fmpBenchmark.discounted_cash_flow?.dcf}
                  currency={currency}
                />
                <MoneyRow
                  label="FMP levered DCF"
                  value={fmpBenchmark.levered_dcf?.dcf}
                  currency={currency}
                />
              </div>
              <div>
                <PercentRow
                  label="WACC to match FMP standard DCF"
                  value={fmpBenchmark.wacc_to_match_standard_dcf}
                />
                <PercentRow
                  label="WACC to match FMP levered DCF"
                  value={fmpBenchmark.wacc_to_match_levered_dcf}
                />
              </div>
            </div>
            <p className="multiples__implied-text multiples__benchmark-note">
              This does not replace the internal model. It shows how far the app's transparent DCF sits from
              FMP's black-box benchmark, and what WACC would make this cash-flow forecast land near FMP's value.
            </p>
          </>
        ) : (
          <p className="multiples__implied-text multiples__benchmark-note">
            Add <span className="mono">FMP_API_KEY</span> to the backend environment to show FMP's standard and
            levered DCF values here as a benchmark.
          </p>
        )}
      </div>

      <div className="multiples__implied-growth">
        <p className="multiples__group-label">Reverse DCF: what would justify the current price</p>
        {impliedGrowthPct !== null ? (
          <p className="multiples__implied-text">
            Holding WACC, margins and reinvestment fixed, the market's current price implies roughly{' '}
            <span className="mono multiples__implied-number">{impliedGrowthPct.toFixed(1)}%</span> annual
            revenue growth. Your growth assumption is{' '}
            <span className="mono multiples__implied-number">{yourGrowthPct.toFixed(1)}%</span>.
          </p>
        ) : (
          <p className="multiples__implied-text">
            No growth rate within a wide range (-50% to +200% a year) would make this DCF match the
            current price with every other assumption held fixed. Closing the gap would need a change to
            WACC, margins or reinvestment, not just growth.
          </p>
        )}

        {impliedDiscountPct !== null ? (
          <p className="multiples__implied-text">
            Holding growth and cash-flow assumptions fixed, the current price implies a WACC of about{' '}
            <span className="mono multiples__implied-number">{impliedDiscountPct.toFixed(1)}%</span>. Your
            model WACC is{' '}
            <span className="mono multiples__implied-number">{yourDiscountPct.toFixed(1)}%</span>. If the
            implied WACC is far below your model WACC, the low fair value is an assumptions problem, not
            a math/display bug.
          </p>
        ) : (
          <p className="multiples__implied-text">
            The model could not solve a sensible market-implied WACC for this set of assumptions.
          </p>
        )}
      </div>

      {hasMismatch && (
        <p className="multiples__flag">
          The DCF-implied P/E and the market's trailing P/E disagree by more than 20%. That is worth
          a closer look before trusting either number on its own.
        </p>
      )}
    </div>
  );
}
