import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { getFilter } from '../../filters/api'
import {
  DENSITY_LABELS,
  LANGUAGE_LABELS,
  PROGRESSION_LABELS,
  SEGMENT_LABELS,
  WORD_LEVEL_LABELS,
} from '../../filters/labels'
import { PageLayout } from '../../../shared/components/PageLayout'
import { getStoryPreview, getStorySegments, listStories } from '../../stories/api'
import { deleteProgress, getProgress } from '../../progress/api'
import { useProgressSaver } from '../../progress/useProgressSaver'
import { useGeneratedAudio } from '../hooks/useGeneratedAudio'
import { AudioPlayer } from './AudioPlayer'
import { selectSwapIds } from '../swaps'
import { BilingualText } from './BilingualText'
import { ResumeCard } from './ResumeCard'
import { DensityStrip } from './DensityStrip'

export function PlayerPage() {
  const { storyId } = useParams<{ storyId: string }>()
  const [searchParams] = useSearchParams()
  // Outra história ou outro filtro: recomeça do zero (polling, frase atual e URLs)
  return <PlayerPageContent key={`${storyId}-${searchParams.get('filter')}`} />
}

function PlayerPageContent() {
  const { storyId: storyParam } = useParams<{ storyId: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const storyId = Number(storyParam)
  const filterParam = Number(searchParams.get('filter'))
  const filterId = Number.isInteger(filterParam) && filterParam > 0 ? filterParam : null
  const validStory = Number.isInteger(storyId) && storyId > 0

  const stories = useQuery({ queryKey: ['stories'], queryFn: listStories })
  const filter = useQuery({
    queryKey: ['filter', filterId],
    queryFn: () => getFilter(filterId as number),
    enabled: filterId !== null,
    retry: false,
  })
  // Retomar de onde parou: com progresso salvo, o usuário escolhe continuar ou recomeçar antes de tocar
  const [choice, setChoice] = useState<'pending' | 'resume' | 'restart'>('pending')
  const hasFilter = validStory && filterId !== null
  const progress = useQuery({
    queryKey: ['progress', storyId],
    queryFn: () => getProgress(storyId),
    enabled: hasFilter,
    retry: false,
    // Cada abertura do player lê o progresso de novo (ele muda a cada escuta)
    staleTime: 0,
    gcTime: 0,
  })
  const saved = progress.data && !progress.data.completed ? progress.data : null
  // Só vale oferecer retomar se o usuário já avançou alguma coisa
  const resumable = saved !== null && (saved.segment_position > 0 || saved.offset_ms >= 1000)
  // Sem filtro, ou sem progresso, ou com a história concluída, ou se a consulta falhou: começa do início
  const resolved = !hasFilter || choice !== 'pending' || progress.isError || (progress.isSuccess && !resumable)
  const resuming = choice === 'resume' && saved !== null

  // Gera o áudio com o filtro e toca frase a frase, conforme cada uma fica pronta
  const audio = useGeneratedAudio(validStory ? storyId : NaN, filterId, {
    startPosition: resuming ? saved.segment_position : 0,
    hold: !resolved,
  })

  // Progresso: a posição é salva sozinha (a cada 5 s, ao pausar e ao sair); o usuário não percebe
  const [playing, setPlaying] = useState(false)
  const offsetMs = useRef(0)
  const onTick = useCallback((seconds: number) => {
    offsetMs.current = seconds * 1000
  }, [])
  const currentSegmentId = audio.current?.segment_id ?? null
  const currentPosition = audio.current?.position ?? null
  // Nova frase: o ponto dentro da anterior não vale mais
  useEffect(() => {
    offsetMs.current = 0
  }, [currentSegmentId])
  const { markCompleted } = useProgressSaver({
    storyId,
    filterId,
    enabled: hasFilter && resolved, // antes da escolha, salvar apagaria o progresso antigo
    playing,
    getPosition: () =>
      currentPosition === null ? null : { segmentPosition: currentPosition, offsetMs: offsetMs.current },
  })
  const lastPosition = audio.segments.length ? audio.segments[audio.segments.length - 1].position : null
  useEffect(() => {
    if (audio.finished && lastPosition !== null) markCompleted({ segmentPosition: lastPosition, offsetMs: 0 })
  }, [audio.finished, lastPosition, markCompleted])

  const segments = useQuery({
    queryKey: ['segments', storyId],
    queryFn: () => getStorySegments(storyId),
    enabled: validStory,
    retry: false,
  })

  const title = stories.data?.find((s) => s.id === storyId)?.title ?? 'Sua história'
  const rules = filter.data?.rules

  const swapIds = useMemo(
    () => (rules && segments.data ? selectSwapIds(segments.data.segments, rules) : new Set<number>()),
    [rules, segments.data],
  )
  // Faixa de densidade: só na densidade crescente (Cenário C), com o perfil por frase calculado pela prévia
  const increasing = rules?.progression === 'increasing'
  const preview = useQuery({
    queryKey: ['preview', storyId, filterId],
    queryFn: () => getStoryPreview(storyId, filterId as number),
    enabled: increasing && validStory && filterId !== null,
    retry: false,
  })

  // Resumo do filtro escolhido, mostrado como etiquetas no topo do player
  const chips = rules
    ? [
      `Base: ${LANGUAGE_LABELS[rules.base_language]}`,
      ...rules.segment_types.map((t) => SEGMENT_LABELS[t]),
      ...(rules.word_level ? [`Nível ${WORD_LEVEL_LABELS[rules.word_level].toLowerCase()}`] : []),
      `Densidade ${increasing ? 'final ' : ''}${DENSITY_LABELS[rules.density].toLowerCase()}`,
      ...(increasing ? [`Progressão ${PROGRESSION_LABELS.increasing.toLowerCase()}`] : []),
    ]
    : []

  let audioError: string | null = null
  if (!validStory) audioError = 'História não encontrada.'
  else if (audio.error) audioError = audio.error
  else if (audio.status?.total === 0) audioError = 'Esta história ainda não tem frases para gerar o áudio.'

  const status = audio.status
  // O player aparece assim que existe alguma frase pronta (ou já pulada): não espera a história toda
  const showPlayer =
    resolved && !audioError && status !== null && (audio.src !== null || audio.currentIndex > 0 || audio.finished)
  const showResume = hasFilter && !resolved && progress.isSuccess && resumable && !audioError

  function restart() {
    setChoice('restart')
    // O progresso antigo deixa de valer; se não for possível apagar, o salvamento seguinte o substitui
    deleteProgress(storyId).catch(() => undefined)
  }

  let subtitle: string | undefined
  if (status) {
    const sentence = audio.current ? `Frase ${audio.currentIndex + 1} de ${status.total}` : 'Fim da história'
    subtitle = audio.generating ? `${sentence} · Gerando áudio: ${status.ready}/${status.total} frases` : sentence
  }

  let waitingMessage: string | null = null
  if (audio.waiting) {
    waitingMessage =
      audio.current?.status === 'ready' ? 'Carregando a próxima frase...' : 'Gerando o áudio da próxima frase...'
  }

  const notice =
    audio.skippedCount > 0
      ? `${audio.skippedCount} ${audio.skippedCount === 1 ? 'frase não pôde ser gerada e foi pulada' : 'frases não puderam ser geradas e foram puladas'}.`
      : null

  return (
    <PageLayout>
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-1.5 text-text-muted hover:text-text-primary transition-colors text-sm mb-5"
      >
        <ArrowLeft size={16} />
        Voltar
      </button>

      {validStory && filterId === null ? (
        <div className="rounded-2xl bg-bg-surface border border-border-subtle p-7 shadow-2xl shadow-black/40">
          <p className="font-display text-2xl text-text-primary mb-4">{title}</p>
          <p role="alert" className="text-sm text-text-muted mb-4">
            Escolha um filtro de audição para gerar o áudio desta história.
          </p>
          <Link
            to="/filter"
            className="inline-block text-sm font-medium rounded-xl px-4 py-2 text-bg-deep"
            style={{ backgroundColor: 'var(--color-accent-en)' }}
          >
            Escolher filtro
          </Link>
        </div>
      ) : showResume && saved ? (
        <ResumeCard
          title={title}
          segmentPosition={saved.segment_position}
          offsetMs={saved.offset_ms}
          total={segments.data?.segments.length ?? status?.total ?? null}
          onContinue={() => setChoice('resume')}
          onRestart={restart}
        />
      ) : showPlayer ? (
        <>
          <AudioPlayer
            src={audio.src}
            title={title}
            chips={chips}
            autoPlay
            onEnded={audio.next}
            subtitle={subtitle}
            waitingMessage={waitingMessage}
            notice={notice}
            onPlayingChange={setPlaying}
            onTick={onTick}
            startAt={resuming && audio.current?.position === saved.segment_position ? saved.offset_ms / 1000 : undefined}
          />
          {increasing && preview.data && (
            <DensityStrip
              profile={preview.data.density_profile}
              currentSegmentId={audio.current?.segment_id ?? null}
              onSelect={audio.goTo}
            />
          )}
          {audio.finished && (
            <div className="flex items-center justify-center gap-5 mt-3">
              <button
                type="button"
                onClick={audio.restart}
                className="text-sm text-text-muted hover:text-text-primary transition-colors"
              >
                Ouvir de novo
              </button>
              <Link to="/" className="text-sm text-text-muted hover:text-text-primary transition-colors">
                Voltar ao início
              </Link>
            </div>
          )}
        </>
      ) : (
        <div className="rounded-2xl bg-bg-surface border border-border-subtle p-7 shadow-2xl shadow-black/40">
          <p className="font-display text-2xl text-text-primary mb-4">{title}</p>
          {audioError ? (
            <p role="alert" className="text-sm" style={{ color: 'var(--color-accent-pt)' }}>
              {audioError}
            </p>
          ) : (
            <p role="status" className="text-sm text-text-muted">
              {status ? `Gerando áudio: ${status.ready}/${status.total} frases...` : 'Preparando o áudio...'}
            </p>
          )}
        </div>
      )}
      {rules && segments.data && (
        <BilingualText
          segments={segments.data.segments}
          baseLanguage={rules.base_language}
          swapIds={swapIds}
          activeSegmentId={audio.current?.segment_id ?? null}
        />
      )}
      {rules && segments.isError && (
        <p className="text-sm mt-4 text-center" style={{ color: 'var(--color-accent-pt)' }}>
          Não foi possível carregar o texto da história.
        </p>
      )}

    </PageLayout>
  )
}
