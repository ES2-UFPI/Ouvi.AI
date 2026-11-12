import type { BaseLanguage, Density, Progression, SegmentType, WordLevel } from './api'

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
  advanced_vocabulary:
    'História em português; as palavras raras são faladas em inglês. Ex.: "A raposa estava faminta (famished)."',
}
export const WORD_LEVEL_HINTS: Record<WordLevel, string> = {
  intermediate: 'Troca as palavras pouco frequentes e as raras.',
  advanced: 'Troca só as palavras raras (menos trocas).',
}

export const PROGRESSION_LABELS: Record<Progression, string> = { constant: 'Constante', increasing: 'Crescente' }
export const PROGRESSION_HINTS: Record<Progression, string> = {
  constant: 'A mesma proporção de trocas do começo ao fim da história.',
  increasing: 'Começa com poucas trocas e aumenta até o final: metade da densidade no início, uma vez e meia no fim.',
}
// Nome de cada terço da história na densidade crescente (swaps.ts: PHASE_WEIGHTS)
export const PHASE_LABELS = ['Início', 'Meio', 'Fim'] as const
