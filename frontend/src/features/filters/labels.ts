import type { BaseLanguage, Density, SegmentType } from './api'

export const LANGUAGE_LABELS: Record<BaseLanguage, string> = { pt: 'Português', en: 'English' }
export const SEGMENT_LABELS: Record<SegmentType, string> = { phrasal_verbs: 'Phrasal verbs' }
export const DENSITY_LABELS: Record<Density, string> = { low: 'Baixa', medium: 'Média', high: 'Alta' }
