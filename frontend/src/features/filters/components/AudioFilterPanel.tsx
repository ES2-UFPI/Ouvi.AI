import { useState } from 'react'
import axios from 'axios'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ChevronDown, Headphones, SlidersHorizontal } from 'lucide-react'
import { listStories } from '../../stories/api'
import {
  createFilter,
  getFilterOptions,
  listFilters,
  updateFilter,
  type BaseLanguage,
  type Density,
  type FilterOptions,
  type FilterPayload,
  type FilterRules,
  type SegmentType,
  type WordLevel,
} from '../api'
import {
  DENSITY_LABELS,
  LANGUAGE_LABELS,
  SEGMENT_HINTS,
  SEGMENT_LABELS,
  WORD_LEVEL_HINTS,
  WORD_LEVEL_LABELS,
} from '../labels'

// Cópia da tabela do backend, usada só enquanto GET /filters/options não responde (ou se ele falhar)
const FALLBACK_OPTIONS: FilterOptions = {
  scenarios: [
    { base_language: 'pt', segment_types: ['phrasal_verbs'], word_levels: [], description: '' },
    {
      base_language: 'en',
      segment_types: ['difficult_words'],
      word_levels: ['intermediate', 'advanced'],
      description: '',
    },
  ],
  densities: ['low', 'medium', 'high'],
  word_levels: ['intermediate', 'advanced'],
}

// Mensagens da API (422) em português; o Pydantic começa cada uma com "Value error, "
function saveErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error) && error.response?.status === 422) {
    const detail: unknown = error.response.data?.detail
    if (Array.isArray(detail)) {
      const messages = detail
        .map((d: { msg?: unknown }) => (typeof d?.msg === 'string' ? d.msg.replace(/^Value error, /, '') : null))
        .filter((m): m is string => !!m)
      if (messages.length) return `Filtro inválido: ${messages.join(' ')}`
    }
    if (typeof detail === 'string') return `Filtro inválido: ${detail}`
  }
  return 'Não foi possível salvar o filtro. Tente novamente.'
}

const SECTION_TITLE = 'block text-xs uppercase tracking-wider text-text-muted mb-2.5'

interface ChoiceProps {
  type: 'radio' | 'checkbox'
  name?: string
  checked: boolean
  onChange: () => void
  label: string
  accent: string
  badge?: string
  center?: boolean
}

// Opção em forma de cartão. O input de verdade continua na tela (só escondido), então o teclado
// e os leitores de tela funcionam; o cartão acende com a cor do `accent` quando marcado.
function Choice({ type, name, checked, onChange, label, accent, badge, center }: ChoiceProps) {
  return (
    <label
      className={`flex items-center gap-2.5 rounded-xl border px-3.5 py-3 text-sm cursor-pointer transition-colors focus-within:ring-2 focus-within:ring-accent-en ${
        center ? 'justify-center' : ''
      } ${checked ? 'text-text-primary' : 'text-text-muted hover:border-text-muted'}`}
      style={{
        borderColor: checked ? accent : 'var(--color-border-subtle)',
        backgroundColor: checked ? `color-mix(in srgb, ${accent} 14%, transparent)` : 'transparent',
      }}
    >
      <input type={type} name={name} checked={checked} onChange={onChange} className="sr-only" />
      {badge && (
        <span
          aria-hidden="true"
          className="text-[10px] font-bold rounded-md px-1.5 py-0.5"
          style={{ backgroundColor: accent, color: 'var(--color-bg-deep)' }}
        >
          {badge}
        </span>
      )}
      {label}
    </label>
  )
}

interface FormValues {
  baseLanguage: BaseLanguage | null
  segmentTypes: SegmentType[]
  density: Density
  wordLevel: WordLevel | null
}

// Começa vazio de propósito: o usuário precisa escolher o idioma base e o tipo de trecho
const EMPTY_FORM: FormValues = { baseLanguage: null, segmentTypes: [], density: 'medium', wordLevel: null }

export function AudioFilterPanel() {
  const queryClient = useQueryClient()
  const [selectedStory, setSelectedStory] = useState<number | null>(null)
  // Só guarda o que o usuário mexeu; sem edição, o formulário mostra o filtro salvo
  const [draft, setDraft] = useState<FormValues | null>(null)

  const stories = useQuery({ queryKey: ['stories'], queryFn: listStories })
  const filters = useQuery({ queryKey: ['filters'], queryFn: listFilters })
  // A tela só oferece as combinações que a API aceita
  const options = useQuery({ queryKey: ['filter-options'], queryFn: getFilterOptions, staleTime: Infinity })
  const { scenarios, densities } = options.data ?? FALLBACK_OPTIONS
  const languages = scenarios.map((s) => s.base_language)

  const storyId = selectedStory ?? stories.data?.[0]?.id ?? null
  // Um filtro por história: o filtro salvo da história escolhida é o que reaparece ao reabrir a tela
  const saved = filters.data?.find((f) => f.story_id === storyId)
  const savedForm: FormValues = saved
    ? {
        baseLanguage: saved.rules.base_language,
        segmentTypes: saved.rules.segment_types,
        density: saved.rules.density,
        wordLevel: saved.rules.word_level ?? null,
      }
    : EMPTY_FORM
  const { baseLanguage, segmentTypes, density, wordLevel } = draft ?? savedForm
  const scenario = scenarios.find((s) => s.base_language === baseLanguage)
  // Só os tipos (e níveis) do cenário do idioma base escolhido
  const allowedTypes = scenario?.segment_types ?? []
  const wordLevels = scenario?.word_levels ?? []
  const needsLevel = wordLevels.length > 0

  function edit(patch: Partial<FormValues>) {
    setDraft({ baseLanguage, segmentTypes, density, wordLevel, ...patch })
  }

  function changeLanguage(lang: BaseLanguage) {
    if (lang === baseLanguage) return
    // Outro idioma base é outro cenário: os tipos e o nível escolhidos antes deixam de valer
    edit({ baseLanguage: lang, segmentTypes: [], wordLevel: null })
  }

  function changeStory(id: number) {
    setSelectedStory(id)
    setDraft(null)
  }

  const save = useMutation({
    mutationFn: (payload: FilterPayload) =>
      saved ? updateFilter(saved.id, payload) : createFilter(payload),
    // Espera a lista atualizar antes de largar o rascunho, para o formulário não piscar o valor antigo
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['filters'] })
      setDraft(null)
    },
  })

  function toggleSegmentType(type: SegmentType) {
    edit({
      segmentTypes: segmentTypes.includes(type)
        ? segmentTypes.filter((t) => t !== type)
        : [...segmentTypes, type],
    })
  }

  // Um filtro antigo pode ter um tipo que o cenário não aceita mais: esse tipo não conta nem é enviado
  const validTypes = segmentTypes.filter((t) => allowedTypes.includes(t))
  const canSave =
    storyId !== null && baseLanguage !== null && validTypes.length > 0 && (!needsLevel || wordLevel !== null)
  const unchanged =
    saved !== undefined &&
    saved.rules.base_language === baseLanguage &&
    saved.rules.density === density &&
    (saved.rules.word_level ?? null) === (needsLevel ? wordLevel : null) &&
    saved.rules.segment_types.length === segmentTypes.length &&
    saved.rules.segment_types.every((t) => segmentTypes.includes(t))

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!canSave) return
    const rules: FilterRules = { base_language: baseLanguage, segment_types: validTypes, density }
    // O nível só vai no cenário que o usa; nos outros a API recusa o campo
    if (needsLevel && wordLevel) rules.word_level = wordLevel
    save.mutate({ story_id: storyId, rules })
  }

  const loadFailed = stories.isError || filters.isError

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-2xl bg-bg-surface border border-border-subtle p-7 shadow-2xl shadow-black/40"
    >
      <div className="flex items-center gap-3 mb-1">
        <span
          className="w-10 h-10 rounded-xl flex items-center justify-center"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--color-accent-pt) 15%, transparent)',
            color: 'var(--color-accent-pt)',
          }}
        >
          <SlidersHorizontal size={20} />
        </span>
        <h2 className="font-display text-2xl text-text-primary">Filtro de Audição</h2>
      </div>
      <p className="text-text-muted text-sm mb-7">Defina quando o áudio troca de idioma.</p>

      {loadFailed && (
        <p role="alert" className="text-sm mb-5" style={{ color: 'var(--color-accent-pt)' }}>
          Não foi possível carregar os dados. Tente novamente em instantes.
        </p>
      )}

      <label htmlFor="story" className={SECTION_TITLE}>
        História
      </label>
      <div className="relative mb-6">
        <select
          id="story"
          value={storyId ?? ''}
          onChange={(e) => changeStory(Number(e.target.value))}
          disabled={!stories.data?.length}
          className="w-full appearance-none rounded-xl bg-bg-deep border border-border-subtle text-text-primary pl-4 pr-10 py-3 focus:outline-none focus:border-accent-en"
        >
          {stories.data?.map((story) => (
            <option key={story.id} value={story.id}>
              {story.title}
            </option>
          ))}
        </select>
        <ChevronDown
          size={18}
          className="absolute right-3.5 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none"
        />
      </div>

      <fieldset className="mb-6">
        <legend className={SECTION_TITLE}>Idioma base</legend>
        <div className="grid grid-cols-2 gap-3">
          {languages.map((lang) => (
            <Choice
              key={lang}
              type="radio"
              name="base-language"
              checked={baseLanguage === lang}
              onChange={() => changeLanguage(lang)}
              label={LANGUAGE_LABELS[lang]}
              badge={lang.toUpperCase()}
              accent={lang === 'pt' ? 'var(--color-accent-pt)' : 'var(--color-accent-en)'}
            />
          ))}
        </div>
      </fieldset>

      <fieldset className="mb-6">
        <legend className={SECTION_TITLE}>Tipo de trecho</legend>
        {baseLanguage === null ? (
          <p className="text-xs text-text-muted">Escolha o idioma base para ver os tipos de trecho.</p>
        ) : (
          <div className="space-y-2">
            {allowedTypes.map((type) => (
              <div key={type}>
                <Choice
                  type="checkbox"
                  checked={segmentTypes.includes(type)}
                  onChange={() => toggleSegmentType(type)}
                  label={SEGMENT_LABELS[type]}
                  accent="var(--color-accent-en)"
                />
                {SEGMENT_HINTS[type] && <p className="text-xs text-text-muted mt-1.5">{SEGMENT_HINTS[type]}</p>}
              </div>
            ))}
          </div>
        )}
      </fieldset>

      {needsLevel && (
        <fieldset className="mb-6">
          <legend className={SECTION_TITLE}>Nível das palavras</legend>
          <div className="grid grid-cols-2 gap-3">
            {wordLevels.map((level) => (
              <Choice
                key={level}
                type="radio"
                name="word-level"
                checked={wordLevel === level}
                onChange={() => edit({ wordLevel: level })}
                label={WORD_LEVEL_LABELS[level]}
                accent="var(--color-accent-en)"
                center
              />
            ))}
          </div>
          {wordLevel && <p className="text-xs text-text-muted mt-1.5">{WORD_LEVEL_HINTS[wordLevel]}</p>}
        </fieldset>
      )}

      <fieldset className="mb-7">
        <legend className={SECTION_TITLE}>Densidade</legend>
        <div className="grid grid-cols-3 gap-3">
          {densities.map((d) => (
            <Choice
              key={d}
              type="radio"
              name="density"
              checked={density === d}
              onChange={() => edit({ density: d })}
              label={DENSITY_LABELS[d]}
              accent="var(--color-accent-pt)"
              center
            />
          ))}
        </div>
      </fieldset>

      {!canSave && storyId !== null && (
        <p className="text-xs text-text-muted mb-3">
          {needsLevel
            ? 'Escolha o idioma base, pelo menos um tipo de trecho e o nível das palavras para salvar.'
            : 'Escolha o idioma base e pelo menos um tipo de trecho para salvar.'}
        </p>
      )}

      <button
        type="submit"
        disabled={!canSave || save.isPending}
        className="w-full rounded-xl py-3 font-medium text-bg-deep transition hover:brightness-110 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:brightness-100"
        style={{ backgroundColor: 'var(--color-accent-pt)' }}
      >
        {save.isPending ? 'Salvando...' : 'Salvar filtro'}
      </button>

      <div aria-live="polite" className="min-h-5 mt-2 text-xs text-center">
        {save.isSuccess && unchanged && <span style={{ color: 'var(--color-accent-en)' }}>Filtro salvo.</span>}
        {save.isError && (
          <span role="alert" style={{ color: 'var(--color-accent-pt)' }}>
            {saveErrorMessage(save.error)}
          </span>
        )}
      </div>

      {saved && unchanged ? (
        <Link
          to={`/player/${storyId}?filter=${saved.id}`}
          className="mt-3 w-full flex items-center justify-center gap-2 rounded-xl py-3 font-medium text-bg-deep transition hover:brightness-110"
          style={{ backgroundColor: 'var(--color-accent-en)' }}
        >
          <Headphones size={18} />
          Ouvir
        </Link>
      ) : (
        <button
          type="button"
          disabled
          className="mt-3 w-full flex items-center justify-center gap-2 rounded-xl py-3 font-medium text-bg-deep opacity-40 cursor-not-allowed"
          style={{ backgroundColor: 'var(--color-accent-en)' }}
        >
          <Headphones size={18} />
          Ouvir
        </button>
      )}
      {saved && !unchanged && (
        <p className="text-xs text-text-muted mt-2 text-center">Salve as alterações para ouvir com este filtro.</p>
      )}
    </form>
  )
}
