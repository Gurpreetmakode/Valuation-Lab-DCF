import './EmptyState.css';

export function EmptyState() {
  return (
    <div className="empty-state">
      <p className="empty-state__eyebrow">No ticker yet</p>
      <h2 className="empty-state__heading">Type a ticker above to get its fair value.</h2>
      <p className="empty-state__body">
        Works best for large, profitable, non-financial companies. Banks and loss-making
        companies need a different valuation approach, so they will show a caveat instead
        of a misleading number.
      </p>
    </div>
  );
}
