import axios from 'axios'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { getFilter } from '../../filters/api'
import { DENSITY_LABELS, LANGUAGE_LABELS, SEGMENT_LABELS } from '../../filters/labels'
import { PageLayout } from '../../../shared/components/PageLayout'
import { listStories } from '../../stories/api'
import { audioKeyForStory, getAudioUrl } from '../api'
import { AudioPlayer } from './AudioPlayer'

export function PlayerPage() {
  const { storyId: storyParam } = useParams<{ storyId: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const storyId = Number(storyParam)
  const filterId = Number(searchParams.get('filter'))
  const validStory = Number.isInteger(storyId) && storyId > 0

  const stories = useQuery({ queryKey: ['stories'], queryFn: listStories })
  const filter = useQuery({
    queryKey: ['filter', filterId],
    queryFn: () => getFilter(filterId),
    enabled: Number.isInteger(filterId) && filterId > 0,
    retry: false,
  })
  // A URL assinada vale por uma hora: guardá-la em cache evita pedir outra a cada visita
  const audio = useQuery({
    queryKey: ['audio-url', storyId],
    queryFn: () => getAudioUrl(audioKeyForStory(storyId)),
    enabled: validStory,
    retry: false,
    staleTime: 30 * 60 * 1000,
  })

  const title = stories.data?.find((s) => s.id === storyId)?.title ?? 'Sua história'
  const rules = filter.data?.rules
  // Resumo do filtro escolhido, mostrado como etiquetas no topo do player
  const chips = rules
    ? [
        `Base: ${LANGUAGE_LABELS[rules.base_language]}`,
        ...rules.segment_types.map((t) => SEGMENT_LABELS[t]),
        `Densidade ${DENSITY_LABELS[rules.density].toLowerCase()}`,
      ]
    : []

  let audioError: string | null = null
  if (!validStory) audioError = 'História não encontrada.'
  else if (audio.isError) {
    audioError =
      axios.isAxiosError(audio.error) && audio.error.response?.status === 404
        ? 'O áudio desta história ainda não foi gerado.'
        : 'Não foi possível obter o áudio agora. Tente novamente em instantes.'
  }

  return (
    <PageLayout>
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-1.5 text-text-muted hover:text-text-primary transition-colors text-sm mb-5"
      >
        <ArrowLeft size={16} />
        Voltar
      </button>

      {audio.data ? (
        <AudioPlayer src={audio.data.url} title={title} chips={chips} />
      ) : (
        <div className="rounded-2xl bg-bg-surface border border-border-subtle p-7 shadow-2xl shadow-black/40">
          <p className="font-display text-2xl text-text-primary mb-4">{title}</p>
          {audioError ? (
            <p role="alert" className="text-sm" style={{ color: 'var(--color-accent-pt)' }}>
              {audioError}
            </p>
          ) : (
            <p role="status" className="text-sm text-text-muted">
              Carregando áudio...
            </p>
          )}
        </div>
      )}
    </PageLayout>
  )
}
