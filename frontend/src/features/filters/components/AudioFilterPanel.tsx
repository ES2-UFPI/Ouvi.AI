import { useFilterStore } from '../store'
import { useEffect, useRef } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { getFilterPreference, saveFilterPreference } from '../api'

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

  const hydrated = useRef(false)
  const saveTimer = useRef<ReturnType<typeof setTimeout>>(0) // Adicionado o 0 temporariamente

  const { data, isSuccess, isError } = useQuery({
    queryKey: ['filter-preference'],
    queryFn: getFilterPreference,
    retry: false,
  })

  const saveMutation = useMutation({ mutationFn: saveFilterPreference })

  // Carrega a preferência salva (uma única vez, quando chega)
  useEffect(() => {
    if (isSuccess && data && !hydrated.current) {
      setPtRatio(data.pt_ratio)
      hydrated.current = true
    }
  }, [isSuccess, data, setPtRatio])

  // Se não existe preferência salva ainda (ex: primeiro acesso, 404),
  // libera o salvamento mesmo assim a partir da próxima mudança
  useEffect(() => {
    if (isError) hydrated.current = true
  }, [isError])

  useEffect(() => {
    return () => clearTimeout(saveTimer.current)
  }, [])

  function handleChange(value: number) {
    setPtRatio(value)

    // Evita salvar o valor padrão (50) por cima da preferência
    // real do usuário, antes do GET inicial terminar
    if (!hydrated.current) return

    clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(() => {
      saveMutation.mutate(value)
    }, 600)
  }

  return (
    <div className="rounded-xl bg-bg-surface border border-border-subtle p-5">
      <div className="flex items-center justify-between mb-1">
        <h3 className="font-display text-lg text-text-primary">Filtro de Audição</h3>
        {saveMutation.isPending && (
          <span className="text-xs text-text-muted">Salvando...</span>
        )}
        {saveMutation.isSuccess && !saveMutation.isPending && (
          <span className="text-xs" style={{ color: 'var(--color-accent-en)' }}>
            Salvo
          </span>
        )}
      </div>
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
        onChange={(e) => handleChange(Number(e.target.value))}
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
            onClick={() => handleChange(preset.value)}
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
  
  