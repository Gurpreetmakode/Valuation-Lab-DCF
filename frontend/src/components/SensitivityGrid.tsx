import type { CSSProperties } from 'react';
import './SensitivityGrid.css';
import { formatMoney } from '../currency';
import type { SensitivityGrid as SensitivityGridType } from '../types';

interface SensitivityGridProps {
  grid: SensitivityGridType;
  currentPrice: number;
  currency?: string;
}

/** Shades a cell by how far its fair value sits from the current price:
 * a gentle tint at the 10% threshold, deepening toward a 50%+ gap, so the
 * table communicates magnitude, not just direction. */
function cellStyle(value: number | null, currentPrice: number): CSSProperties {
  if (value === null || !currentPrice) return {};
  const gap = (value - currentPrice) / currentPrice;
  const intensity = Math.min(Math.abs(gap) / 0.5, 1); // fully saturated by a 50% gap
  if (Math.abs(gap) < 0.1) return {};
  if (gap > 0) {
    return { backgroundColor: `rgba(20, 164, 77, ${0.08 + intensity * 0.22})`, color: 'var(--moss)', fontWeight: 600 };
  }
  return { backgroundColor: `rgba(229, 72, 77, ${0.08 + intensity * 0.22})`, color: 'var(--ember)', fontWeight: 600 };
}

export function SensitivityGrid({ grid, currentPrice, currency = '$' }: SensitivityGridProps) {
  return (
    <div className="sensitivity">
      <h2 className="sensitivity__title">Sensitivity</h2>
      <p className="sensitivity__subtitle">
        Fair value per share at combinations of growth and discount rate. Rows are discount rate,
        columns are growth rate. Deeper color means a bigger gap from the current price. The boxed
        cell is where your current assumptions sit.
      </p>
      <div className="sensitivity__scroll">
        <table className="sensitivity__table mono">
          <thead>
            <tr>
              <th className="sensitivity__corner">disc \ growth</th>
              {grid.growth_rates.map((g, colIndex) => (
                <th key={g} className={colIndex === grid.current_cell.col ? 'sensitivity__current-axis' : ''}>
                  {g.toFixed(1)}%
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {grid.discount_rates.map((d, rowIndex) => (
              <tr key={d}>
                <th scope="row" className={rowIndex === grid.current_cell.row ? 'sensitivity__current-axis' : ''}>
                  {d.toFixed(1)}%
                </th>
                {grid.values[rowIndex].map((value, colIndex) => {
                  const isCurrent = rowIndex === grid.current_cell.row && colIndex === grid.current_cell.col;
                  return (
                    <td
                      key={colIndex}
                      style={cellStyle(value, currentPrice)}
                      className={isCurrent ? 'sensitivity__cell--current' : ''}
                      title={isCurrent ? 'Your current assumptions' : undefined}
                    >
                      {value !== null ? formatMoney(value, currency, 0) : '—'}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
