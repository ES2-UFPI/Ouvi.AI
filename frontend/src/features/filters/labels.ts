import type { BaseLanguage, Density, SegmentType, WordLevel } from './api'

export const LANGUAGE_LABELS: Record<BaseLanguage, string> = { pt: 'Português', en: 'English' }
export const SEGMENT_LABELS: Record<SegmentType, string> = {
  phrasal_verbs: 'Phrasal verbs',
  difficult_words: 'Palavras difíceis',
  advanced_vocabulary: 'Vocabulário avançado',
}
export const DENSITY_LABELS: Record<Density, string> = { low: 'Baixa', medium: 'Média', high: 'Alta' }
export const WORD_LEVEL_LABELS: Record<WordLevel, string> = { intermediate: 'Intermediário', advanced: 'Avançado' }

// Microtexto de cada tipo de trecho, com um exemplo do que muda no áudio
export const SEGMENT_HINTS: Partial<Record<SegmentType, string>> = {
  phrasal_verbs: 'História em português; os phrasal verbs são falados em inglês. Ex.: "Ele vestiu (put on) o casaco."',
  difficult_words:
    'História em inglês; as palavras difíceis são faladas em português. Ex.: "The fox was famished (faminta)."',
}
export const WORD_LEVEL_HINTS: Record<WordLevel, string> = {
  intermediate: 'Troca as palavras pouco frequentes e as raras.',
  advanced: 'Troca só as palavras raras (menos trocas).',
}
