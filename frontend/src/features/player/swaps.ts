import type { Density } from '../filters/api'
import type { StorySegment } from '../stories/api'

// ATENÇÃO: RESOLVER COM OS MENINOS DO BACK QUAIS AS PROPORÇÕES ASSUMIDAS PARA CADA DENSIDADE. 
// Se a US definir outras, só estes números mudam.
export const DENSITY_SHARE: Record<Density, [number, number]> = {
  low: [1, 3], // 1 de cada 3 trechos
  medium: [2, 3], // 2 de cada 3
  high: [1, 1], // todos
}

// Escolhe, de forma estável e espalhada pela história, quais anotações viram troca - alterar em função da densidade escolhida
export function selectSwapIds(segments: StorySegment[], density: Density): Set<number> {
  const [num, den] = DENSITY_SHARE[density]
  const swappable = segments
    .flatMap((segment) => segment.annotations)
    .filter((a) => a.pt_start !== null && a.pt_end !== null && a.pt_text !== null)

  const selected = new Set<number>()
  swappable.forEach((annotation, i) => {
    if (Math.floor(((i + 1) * num) / den) > Math.floor((i * num) / den)) {
      selected.add(annotation.id)
    }
  })
  return selected
}