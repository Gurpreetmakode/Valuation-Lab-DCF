import './BacktestPanel.css';
import { formatMoney } from '../currency';
import type { BacktestResult } from '../types';

interface BacktestPanelProps {
  backtest: BacktestResult;
  currency?: string;
}

export function BacktestPanel({ backtest, currency = '$' }: BacktestPanelProps) {
  return (
    <div className="backtest">
      <h2 className="backtest__title">Backtest</h2>
      <p className="backtest__subtitle">
        Reruns this same model using only the financial data available at several points in the
        past, then checks whether the price actually moved the direction each estimate expected.
        With only a few checkpoints available from free data, read this as a small sample, not a
        track record.
      </p>

      {!backtest.available && (
        <p className="backtest__unavailable">
          {backtest.reason ?? 'A backtest could not be run for this ticker.'}
        </p>
      )}

      {backtest.available && (
        <>
          <div className="backtest__summary">
            <span className="mono backtest__summary-number">
              {backtest.correct_count} / {backtest.total_count}
            </span>
            <span className="backtest__summary-text">
              historical checkpoints where the price moved the direction the model expected
            </span>
          </div>

          <div className="backtest__scroll">
            <table className="backtest__table mono">
              <thead>
                <tr>
                  <th>As of</th>
                  <th>Model's fair value then</th>
                  <th>Actual price then</th>
                  <th>Price change since</th>
                  <th>Direction</th>
                </tr>
              </thead>
              <tbody>
                {backtest.checkpoints.map((c) => (
                  <tr key={c.as_of_date}>
                    <td>{c.as_of_date}</td>
                    <td>{formatMoney(c.implied_fair_value_then, currency)}</td>
                    <td>{formatMoney(c.actual_price_then, currency)}</td>
                    <td className={c.price_change_pct >= 0 ? 'backtest__positive' : 'backtest__negative'}>
                      {c.price_change_pct > 0 ? '+' : ''}
                      {c.price_change_pct.toFixed(0)}%
                    </td>
                    <td className={c.direction_correct ? 'backtest__positive' : 'backtest__negative'}>
                      {c.direction_correct ? 'Correct' : 'Incorrect'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
