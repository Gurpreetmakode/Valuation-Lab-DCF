import './CaveatBanner.css';

interface CaveatBannerProps {
  reasons: string[];
  warnings: string[];
}

export function CaveatBanner({ reasons, warnings }: CaveatBannerProps) {
  if (reasons.length === 0 && warnings.length === 0) return null;

  return (
    <div className={`caveat ${reasons.length > 0 ? 'caveat--serious' : 'caveat--minor'}`}>
      {reasons.map((reason, i) => (
        <p key={`reason-${i}`} className="caveat__line">
          {reason}
        </p>
      ))}
      {warnings.map((warning, i) => (
        <p key={`warning-${i}`} className="caveat__line caveat__line--minor">
          {warning}
        </p>
      ))}
    </div>
  );
}
