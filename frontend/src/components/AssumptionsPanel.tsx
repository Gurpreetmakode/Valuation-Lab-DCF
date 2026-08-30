import './AssumptionsPanel.css';
import { FIELD_CONFIGS } from '../assumptionFields';
import type { Assumptions, DcfScenario, EditableAssumptionField, OverrideFlags } from '../types';

interface AssumptionsPanelProps {
  values: Assumptions;
  overrides: OverrideFlags;
  scenario: DcfScenario;
  onScenarioChange: (scenario: DcfScenario) => void;
  onChange: (field: EditableAssumptionField, value: number) => void;
  onResetField: (field: EditableAssumptionField) => void;
  onResetAll: () => void;
  onCalculate: () => void;
  isCalculating: boolean;
  hasPendingChanges: boolean;
  modeLabel: string;
  showScenarioSelector?: boolean;
}

const GROUP_LABELS: Record<'core' | 'wacc' | 'operating', string> = {
  core: 'Core assumptions',
  wacc: 'WACC build-up',
  operating: 'Operating assumptions',
};

function formatValue(value: number, isPercent: boolean) {
  return isPercent ? `${(value * 100).toFixed(2)}%` : value.toFixed(2);
}

function inputValue(value: number, isPercent: boolean) {
  return isPercent ? Number((value * 100).toFixed(2)) : Number(value.toFixed(2));
}

function outputValue(rawValue: string, isPercent: boolean) {
  const parsed = Number(rawValue);
  if (!Number.isFinite(parsed)) return null;
  return isPercent ? parsed / 100 : parsed;
}

export function AssumptionsPanel({
  values,
  overrides,
  scenario,
  onScenarioChange,
  onChange,
  onResetField,
  onResetAll,
  onCalculate,
  isCalculating,
  hasPendingChanges,
  modeLabel,
  showScenarioSelector = true,
}: AssumptionsPanelProps) {
  const anyOverridden = Object.values(overrides).some(Boolean);
  const groups: Array<'core' | 'wacc' | 'operating'> = ['core', 'wacc', 'operating'];

  return (
    <div className="assumptions">
      <div className="assumptions__header">
        <div>
          <h2 className="assumptions__title">Assumptions</h2>
          <p className="assumptions__intro">
            Edit assumptions for the {modeLabel}. Sliders and text boxes only stage changes;
            the valuation updates when you press Calculate.
          </p>
        </div>
        <div className="assumptions__actions">
          {anyOverridden && (
            <button type="button" className="assumptions__reset-all" onClick={onResetAll}>
              Reset all to defaults
            </button>
          )}
          <button
            type="button"
            className="assumptions__calculate"
            onClick={onCalculate}
            disabled={isCalculating}
          >
            {isCalculating ? 'Calculating…' : 'Calculate DCF'}
          </button>
        </div>
      </div>

{showScenarioSelector && (
  <>
    <div className="assumptions__scenario-row" aria-label="DCF scenario">
      {(['conservative', 'neutral', 'bullish', 'custom'] as DcfScenario[]).map((item) => (
        <button
          key={item}
          type="button"
          className={`assumptions__scenario ${scenario === item ? 'assumptions__scenario--active' : ''}`}
          onClick={() => onScenarioChange(item)}
        >
          {item === 'custom' ? 'Custom' : item.charAt(0).toUpperCase() + item.slice(1)}
        </button>
      ))}
    </div>

    <p className="assumptions__scenario-help">
      Conservative uses the raw default model. Neutral and Bullish load preset assumptions; press Calculate DCF to apply them.
      Custom is selected automatically when you type or move a slider.
    </p>
  </>
)}

      {hasPendingChanges && (
        <p className="assumptions__pending">
          Assumption edits are staged. Press Calculate DCF to update the fair value and charts.
        </p>
      )}

      {groups.map((group) => (
        <div className="assumptions__group" key={group}>
          <p className="assumptions__group-label">{GROUP_LABELS[group]}</p>
          <div className="assumptions__field-grid">
            {FIELD_CONFIGS.filter((f) => f.group === group).map((field) => (
              <div className="assumptions__field" key={field.key}>
                <div className="assumptions__field-header">
                  <label htmlFor={`${field.key}-range`}>{field.label}</label>
                  <div className="assumptions__field-value-row">
                    <span className="mono assumptions__value">{formatValue(values[field.key], field.isPercent)}</span>
                    {overrides[field.key] && (
                      <button
                        type="button"
                        className="assumptions__field-reset"
                        onClick={() => onResetField(field.key)}
                        title={`Reset ${field.label} to default`}
                        aria-label={`Reset ${field.label} to default`}
                      >
                        ↺
                      </button>
                    )}
                  </div>
                </div>
                <div className="assumptions__input-row">
                  <input
                    id={`${field.key}-range`}
                    type="range"
                    min={field.min}
                    max={field.max}
                    step={field.step}
                    value={values[field.key]}
                    onChange={(e) => onChange(field.key, parseFloat(e.target.value))}
                    className={overrides[field.key] ? 'assumptions__slider--overridden' : ''}
                  />
                  <div className="assumptions__number-wrap">
                    <input
                      aria-label={`${field.label} number input`}
                      className="assumptions__number"
                      type="number"
                      min={field.isPercent ? field.min * 100 : field.min}
                      max={field.isPercent ? field.max * 100 : field.max}
                      step={field.isPercent ? field.step * 100 : field.step}
                      value={inputValue(values[field.key], field.isPercent)}
                      onChange={(e) => {
                        const next = outputValue(e.target.value, field.isPercent);
                        if (next !== null) onChange(field.key, next);
                      }}
                    />
                    {field.isPercent && <span className="assumptions__number-suffix">%</span>}
                  </div>
                </div>
                <p className="assumptions__hint">{field.hint}</p>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
