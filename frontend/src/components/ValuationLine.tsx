import './ValuationLine.css';
import { formatMoney } from '../currency';
import type { Reliability, ValuationSummary } from '../types';

interface ValuationLineProps {
  valuation: ValuationSummary;
  reliability: Reliability;
  currency?: string;
}

const VERDICT_COPY: Record<ValuationSummary['verdict'], string> = {
  undervalued: 'trading below its estimated fair value',
  overvalued: 'trading above its estimated fair value',
  'fairly valued': 'trading close to its estimated fair value',
};

export function ValuationLine({ valuation, reliability, currency = '$' }: ValuationLineProps) {
  const { current_price, fair_value_per_share, gap_percent, verdict } = valuation;

  const low = Math.min(current_price, fair_value_per_share);
  const high = Math.max(current_price, fair_value_per_share);
  const padding = (high - low) * 0.6 || high * 0.15 || 1;
  const rangeMin = Math.max(0, low - padding);
  const rangeMax = high + padding;
  const span = rangeMax - rangeMin || 1;

  const pricePct = ((current_price - rangeMin) / span) * 100;
  const fairPct = ((fair_value_per_share - rangeMin) / span) * 100;

  const accentClass = !reliability.confident
    ? 'unreliable'
    : verdict === 'overvalued'
      ? 'ember'
      : verdict === 'undervalued'
        ? 'moss'
        : 'brass';

  return (
    <div className={`valuation-line ${!reliability.confident ? 'valuation-line--unreliable' : ''}`}>
      <div className="valuation-line__verdict">
        <span className={`valuation-line__badge valuation-line__badge--${accentClass}`}>
          {reliability.confident ? verdict : 'Unreliable result'}
        </span>
        <span className="valuation-line__verdict-text">
          {reliability.confident
            ? `${Math.abs(Math.round(gap_percent))}% ${VERDICT_COPY[verdict]}`
            : reliability.reason}
        </span>
      </div>

      <div
        className="valuation-line__ruler"
        role="img"
        aria-label={`Current price ${formatMoney(current_price, currency)}, fair value ${formatMoney(fair_value_per_share, currency)}`}
      >
        <div className="valuation-line__track" />
        <div
          className={`valuation-line__bracket valuation-line__bracket--${accentClass}`}
          style={{
            left: `${Math.min(pricePct, fairPct)}%`,
            width: `${Math.abs(fairPct - pricePct)}%`,
          }}
        />
        <div className="valuation-line__pin valuation-line__pin--current" style={{ left: `${pricePct}%` }}>
          <span className="valuation-line__pin-dot" />
          <span className="valuation-line__pin-label mono">
            {formatMoney(current_price, currency)}
            <small>market price</small>
          </span>
        </div>
        <div
          className={`valuation-line__pin valuation-line__pin--fair valuation-line__pin--${accentClass}`}
          style={{ left: `${fairPct}%` }}
        >
          <span className="valuation-line__pin-dot" />
          <span className="valuation-line__pin-label mono">
            {formatMoney(fair_value_per_share, currency)}
            <small>fair value</small>
          </span>
        </div>
      </div>
    </div>
  );
}
