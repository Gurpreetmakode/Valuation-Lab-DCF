import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import './FCFEChart.css';
import type { Projection } from '../types';

interface FCFEChartProps {
  projection: Projection;
  companyName: string;
  currency?: string;
}

const SERIES_LABEL: Record<string, string> = {
  projected: 'Projected FCFF',
  discounted: 'Discounted to present value',
};

function formatBillions(value: number, currency: string) {
  return `${currency}${(value / 1_000_000_000).toFixed(1)}B`;
}

export function FCFEChart({ projection, companyName, currency = '$' }: FCFEChartProps) {
  const data = projection.years.map((year, i) => ({
    year: `Year ${year}`,
    projected: projection.projected_fcfe[i],
    discounted: projection.discounted_fcfe[i],
  }));

  return (
    <div className="fcfe-chart">
      <h2 className="fcfe-chart__title">Projected free cash flow to the firm</h2>
      <p className="fcfe-chart__subtitle">
        {companyName}'s forecast unlevered cash flow, shown both as projected and discounted to present value using WACC.
      </p>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
          <XAxis dataKey="year" tick={{ fontSize: 12, fill: 'var(--slate)' }} axisLine={{ stroke: 'var(--line)' }} tickLine={false} />
          <YAxis
            tickFormatter={(v) => formatBillions(v, currency)}
            tick={{ fontSize: 12, fill: 'var(--slate)' }}
            axisLine={false}
            tickLine={false}
            width={72}
          />
          <Tooltip
            formatter={(value, name) => [formatBillions(Number(value), currency), SERIES_LABEL[name as string] ?? name]}
            contentStyle={{ borderRadius: 3, borderColor: 'var(--line)', fontSize: 13 }}
          />
          <Legend
            formatter={(name) => <span className="fcfe-chart__legend">{SERIES_LABEL[name] ?? name}</span>}
            iconType="square"
            iconSize={10}
          />
          <Bar dataKey="projected" fill="var(--brass-dim)" radius={[2, 2, 0, 0]} name="projected" />
          <Bar dataKey="discounted" fill="var(--brass)" radius={[2, 2, 0, 0]} name="discounted" />
        </BarChart>
      </ResponsiveContainer>
      <p className="fcfe-chart__terminal">
        Terminal value (discounted to today):{' '}
        <span className="mono">{formatBillions(projection.terminal_value_discounted, currency)}</span>
        {' '}— {(projection.terminal_value_share * 100).toFixed(0)}% of enterprise value
      </p>
    </div>
  );
}
