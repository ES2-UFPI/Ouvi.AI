import { useEffect, useState } from 'react'
import { getFullAudio, type FullAudio } from '../api'

/**
 * Busca o áudio único da história (todas as frases num arquivo só) quando a geração terminou.
 *
 * `ready`: a geração acabou (todas as frases prontas ou falhas). Se o áudio único não puder ser obtido
 * (409, rede, formato), `failed` fica verdadeiro e o player segue frase a frase, como antes.
 * `pending`: já dá para pedir, mas ainda não chegou nem falhou.
 */
export function useFullAudio(storyId: number, filterId: number | null, ready: boolean) {
  const [track, setTrack] = useState<FullAudio | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!ready || filterId === null) return
    let cancelled = false
    Promise.resolve()
      .then(() => getFullAudio(storyId, filterId))
      .then((data) => {
        if (cancelled) return
        if (data && data.segments?.length) setTrack(data)
        else setFailed(true)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [ready, storyId, filterId])

  return { track, failed, pending: ready && filterId !== null && track === null && !failed }
}
