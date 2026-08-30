import { Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from 'recharts';
import './PriceHistoryChart.css';
import { formatMoney } from '../currency';
import type { PricePoint } from '../types';

interface PriceHistoryChartProps {
  history: PricePoint[];
  fairValue: number;
  currency?: string;
  isLoading: boolean;
  error: string | null;
}

export function PriceHistoryChart({ history, fairValue, currency = '$', isLoading, error }: PriceHistoryChartProps) {
  const closes = history.map((h) => h.close);
  const dataMin = closes.length ? Math.min(...closes) : 0;
  const dataMax = closes.length ? Math.max(...closes) : 0;
  const midpoint = (dataMin + dataMax) / 2;

  // When the fair value sits far outside the plotted price range, the dashed
  // line collapses into the axis and any label on it just overlaps the tick
  // labels. In that case, skip the on-chart label and explain it in text
  // instead, rather than rendering something unreadable.
  // Recharts clips a ReferenceLine entirely if its value falls outside the
  // Y-axis domain, rather than drawing it at the edge. An axis auto-scaled
  // to price history alone can easily exclude a fair value that sits well
  // below or above that range, so the domain is computed explicitly here to
  // always include both, guaranteeing the line actually renders.
  const domainMin = closes.length ? Math.min(dataMin, fairValue) : fairValue;
  const domainMax = closes.length ? Math.max(dataMax, fairValue) : fairValue;
  const domainPadding = (domainMax - domainMin) * 0.05 || domainMax * 0.05 || 1;
  const yDomain: [number, number] = [Math.max(0, domainMin - domainPadding), domainMax + domainPadding];

  const isFarBelow = closes.length > 0 && fairValue < dataMin * 0.5;
  const isFarAbove = closes.length > 0 && fairValue > dataMax * 1.5;
  const isOffScale = isFarBelow || isFarAbove;
  const labelPosition = fairValue > midpoint ? 'insideBottomRight' : 'insideTopRight';

  return (
    <div className="price-history">
      <h2 className="price-history__title">Price history vs today's fair value</h2>
      <p className="price-history__subtitle">
        5 years of weekly closing prices, with today's computed fair value drawn as a flat reference line.
        The line does not move with history, since it reflects only current assumptions.
      </p>

      {isLoading && <p className="price-history__status">Loading price history…</p>}
      {error && <p className="price-history__status price-history__status--error">{error}</p>}

      {!isLoading && !error && history.length > 0 && (
        <>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={history} margin={{ top: 8, right: 16, left: -12, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11, fill: 'var(--slate)' }}
                axisLine={{ stroke: 'var(--line)' }}
                tickLine={false}
                minTickGap={60}
              />
              <YAxis
                tickFormatter={(v) => formatMoney(v, currency, 0)}
                tick={{ fontSize: 12, fill: 'var(--slate)' }}
                axisLine={false}
                tickLine={false}
                width={92}
                domain={yDomain}
              />
              <Tooltip
                formatter={(value) => [formatMoney(Number(value), currency), 'Close']}
                contentStyle={{ borderRadius: 3, borderColor: 'var(--line)', fontSize: 13 }}
              />
              <ReferenceLine
                y={fairValue}
                stroke="var(--brass)"
                strokeDasharray="4 4"
                strokeWidth={2}
                label={
                  isOffScale
                    ? undefined
                    : {
                        value: `Fair value ${formatMoney(fairValue, currency, 0)}`,
                        position: labelPosition,
                        fill: 'var(--brass)',
                        fontSize: 12,
                      }
                }
              />
              <Line type="monotone" dataKey="close" stroke="var(--ink)" strokeWidth={1.75} dot={false} />
            </LineChart>
          </ResponsiveContainer>

          {isOffScale && (
            <p className="price-history__offscale">
              The computed fair value ({formatMoney(fairValue, currency)}) is{' '}
              {isFarBelow ? 'far below' : 'far above'} the 5-year price range shown, so its reference
              line sits at the very {isFarBelow ? 'bottom' : 'top'} edge of the chart and is easy to miss.
              This usually signals a data or assumption problem worth double-checking rather than a
              genuine {isFarBelow ? '99%+' : 'multiple-fold'} mispricing.
            </p>
          )}
        </>
      )}
    </div>
  );
}
