import './WatchlistPanel.css';
import { formatMoney } from '../currency';
import type { WatchlistEntry } from '../types';

interface WatchlistPanelProps {
  entries: WatchlistEntry[];
  currentTicker: string | null;
  onAdd: () => void;
  onRemove: (ticker: string) => void;
  onSelect: (ticker: string) => void;
}

export function WatchlistPanel({ entries, currentTicker, onAdd, onRemove, onSelect }: WatchlistPanelProps) {
  const sorted = [...entries].sort((a, b) => b.gapPercent - a.gapPercent);
  const alreadySaved = currentTicker ? entries.some((e) => e.ticker === currentTicker) : false;

  return (
    <div className="watchlist">
      <div className="watchlist__header">
        <div>
          <h2 className="watchlist__title">Watchlist</h2>
          <p className="watchlist__subtitle">Saved locally in this browser. Sorted most to least undervalued.</p>
        </div>
        <button className="watchlist__add" onClick={onAdd} disabled={!currentTicker || alreadySaved}>
          {alreadySaved ? 'Saved' : 'Add current ticker'}
        </button>
      </div>

      {sorted.length === 0 && <p className="watchlist__empty">No tickers saved yet.</p>}

      {sorted.length > 0 && (
        <div className="watchlist__scroll">
          <table className="watchlist__table mono">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Fair value</th>
                <th>Market price</th>
                <th>Gap</th>
                <th>Verdict</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((entry) => (
                <tr key={entry.ticker} className={entry.ticker === currentTicker ? 'watchlist__row--active' : ''}>
                  <td>
                    <button className="watchlist__ticker-link" onClick={() => onSelect(entry.ticker)}>
                      {entry.ticker}
                    </button>
                  </td>
                  <td>{formatMoney(entry.fairValue, entry.currency)}</td>
                  <td>{formatMoney(entry.currentPrice, entry.currency)}</td>
                  <td className={entry.gapPercent >= 0 ? 'watchlist__gap--positive' : 'watchlist__gap--negative'}>
                    {entry.gapPercent > 0 ? '+' : ''}
                    {entry.gapPercent.toFixed(0)}%
                  </td>
                  <td className="watchlist__verdict">{entry.verdict}</td>
                  <td>
                    <button className="watchlist__remove" onClick={() => onRemove(entry.ticker)} aria-label={`Remove ${entry.ticker}`}>
                      ×
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
