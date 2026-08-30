import { useState } from 'react';
import './HowItWorks.css';

export function HowItWorks() {
  const [open, setOpen] = useState(false);

  return (
    <div className="how-it-works">
      <button
        className="how-it-works__toggle"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span>How this valuation is calculated</span>
        <span className="how-it-works__chevron" aria-hidden="true">{open ? '−' : '+'}</span>
      </button>

      {open && (
        <div className="how-it-works__body">
          <ol className="how-it-works__steps">
            <li>
              <strong>Revenue is projected forward 5 years</strong> using a growth rate.
              The default is the company's own 5-year historical revenue growth rate (CAGR),
              which you can override with the slider.
            </li>
            <li>
              <strong>Unlevered free cash flow is estimated each year</strong> by applying the
              company's historical average operating margin, tax rate, depreciation, capital
              expenditure, and working capital patterns to that projected revenue.
            </li>
            <li>
              <strong>Each year's cash flow is discounted back to today</strong> using WACC, not just
              cost of equity. The WACC build-up starts with CAPM cost of equity, then blends in
              after-tax cost of debt using the company's debt weight. The key inputs are adjustable
              in the panel.
            </li>
            <li>
              <strong>A terminal value captures everything beyond year 5</strong>, assuming cash
              flow keeps growing at a fixed rate forever after that (defaulted to 2.5% per year,
              also adjustable), then discounts that perpetuity back to today too.
            </li>
            <li>
              <strong>All discounted cash flows are summed into enterprise value</strong>, then net
              debt is subtracted to reach equity value. That equity value is divided by shares
              outstanding to get a fair value per share, which is compared against the current
              market price.
            </li>
          </ol>
          <p className="how-it-works__caveat">
            This is a simplified model. It assumes a constant capital structure, uses book debt as
            a proxy for market-value debt, and holds margins and ratios at their historical average
            rather than modeling them changing over time. It is not suited to banks, insurers,
            loss-making companies, or businesses with too little trading history, all of which get
            a caveat instead of a number.
          </p>
        </div>
      )}
    </div>
  );
}
