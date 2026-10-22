import { useFilterStore } from '../store'

const PRESETS = [
  { label: 'Só PT', value: 100 },
  { label: '70/30', value: 70 },
  { label: '50/50', value: 50 },
  { label: '30/70', value: 30 },
  { label: 'Só EN', value: 0 },
]

export function AudioFilterPanel() {
  const ptRatio = useFilterStore((s) => s.ptRatio)
  const setPtRatio = useFilterStore((s) => s.setPtRatio)
  const enRatio = 100 - ptRatio

  return (
    <div className="rounded-xl bg-bg-surface border border-border-subtle p-5">
      <h3 className="font-display text-lg text-text-primary mb-1">Filtro de Audição</h3>
      <p className="text-text-muted text-sm mb-5">
        Defina quanto da faixa será narrado em cada idioma.
      </p>

      <div className="flex justify-between text-sm mb-2">
        <span style={{ color: 'var(--color-accent-pt)' }}>{ptRatio}% Português</span>
        <span style={{ color: 'var(--color-accent-en)' }}>{enRatio}% English</span>
      </div>

      <input
        type="range"
        min={0}
        max={100}
        step={10}
        value={ptRatio}
        onChange={(e) => setPtRatio(Number(e.target.value))}
        className="pt-en-slider w-full"
        style={{
          background: `linear-gradient(to right, var(--color-accent-pt) 0%, var(--color-accent-pt) ${ptRatio}%, var(--color-accent-en) ${ptRatio}%, var(--color-accent-en) 100%)`,
        }}
        aria-label="Proporção de português na faixa de áudio"
      />

      <div className="flex flex-wrap gap-2 mt-4">
        {PRESETS.map((preset) => (
          <button
            key={preset.value}
            type="button"
            onClick={() => setPtRatio(preset.value)}
            className="text-xs px-2.5 py-1 rounded-full border transition-colors"
            style={{
              borderColor: ptRatio === preset.value ? 'var(--color-text-primary)' : 'var(--color-border-subtle)',
              color: ptRatio === preset.value ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
            }}
          >
            {preset.label}
          </button>
        ))}
      </div>
    </div>
  )
}