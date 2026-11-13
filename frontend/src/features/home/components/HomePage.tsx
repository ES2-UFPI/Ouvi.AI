import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Headphones, LogOut } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../auth/store'
import { listRecentProgress, type Progress } from '../../progress/api'
import { listStories, type Story } from '../../stories/api'
import { getMe } from '../../users/api'
import { PageLayout } from '../../../shared/components/PageLayout'

// Quantas histórias em andamento aparecem em "Continuar ouvindo"
const RECENT_LIMIT = 5

const CARD = 'rounded-2xl bg-bg-surface border border-border-subtle p-5'
const PRIMARY_LINK =
  'inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-medium text-bg-deep transition hover:brightness-110'

function firstName(name: string | undefined) {
  return name?.trim().split(/\s+/)[0] ?? ''
}

function ErrorNotice({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div role="alert" className={`${CARD} text-sm`}>
      <p style={{ color: 'var(--color-accent-pt)' }}>{message}</p>
      <button type="button" onClick={onRetry} className="mt-3 text-text-muted hover:text-text-primary underline">
        Tentar de novo
      </button>
    </div>
  )
}

function Skeleton({ label }: { label: string }) {
  return (
    <div role="status" aria-label={label} className="grid gap-3 sm:grid-cols-2">
      {[0, 1].map((i) => (
        <div key={i} className={`${CARD} h-28 animate-pulse`} />
      ))}
    </div>
  )
}

function ContinueCard({ progress, story }: { progress: Progress; story: Story }) {
  const total = story.segment_count
  const sentence = Math.min(progress.segment_position + 1, total || progress.segment_position + 1)
  const percent = total > 0 ? Math.round((sentence / total) * 100) : 0
  // Sem filtro guardado no progresso, o caminho é escolher um filtro para esta história
  const to = progress.filter_id ? `/player/${story.id}?filter=${progress.filter_id}` : `/filter?story=${story.id}`

  return (
    <li className={CARD}>
      <h3 className="font-display text-lg text-text-primary leading-tight mb-3">{story.title}</h3>
      <div
        role="progressbar"
        aria-label={`Progresso em ${story.title}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-valuetext={`frase ${sentence} de ${total}`}
        className="h-1.5 rounded-full overflow-hidden mb-2"
        style={{ backgroundColor: 'var(--color-border-subtle)' }}
      >
        <div className="h-full rounded-full" style={{ width: `${percent}%`, backgroundColor: 'var(--color-accent-en)' }} />
      </div>
      <p className="text-xs text-text-muted mb-4">
        frase {sentence} de {total}
      </p>
      <Link to={to} className={PRIMARY_LINK} style={{ backgroundColor: 'var(--color-accent-en)' }}>
        {progress.filter_id ? 'Continuar' : 'Escolher filtro'}
      </Link>
    </li>
  )
}

function StoryCard({ story }: { story: Story }) {
  return (
    <li className={`${CARD} flex flex-col`}>
      <h3 className="font-display text-lg text-text-primary leading-tight">{story.title}</h3>
      {story.description && <p className="text-sm text-text-muted mt-1.5">{story.description}</p>}
      <p className="text-xs text-text-muted mt-3 mb-4">
        {story.segment_count} {story.segment_count === 1 ? 'frase' : 'frases'}
      </p>
      <Link
        to={`/filter?story=${story.id}`}
        aria-label={`Ouvir ${story.title}`}
        className={`${PRIMARY_LINK} mt-auto self-start`}
        style={{ backgroundColor: 'var(--color-accent-en)' }}
      >
        <Headphones size={16} aria-hidden="true" />
        Ouvir
      </Link>
    </li>
  )
}

export function HomePage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const logout = useAuthStore((s) => s.logout)

  const me = useQuery({ queryKey: ['me'], queryFn: getMe, retry: false })
  const stories = useQuery({ queryKey: ['stories'], queryFn: listStories })
  // O progresso muda a cada escuta: sempre lê de novo ao voltar para a tela inicial
  const recent = useQuery({
    queryKey: ['progress', 'recent'],
    queryFn: () => listRecentProgress(RECENT_LIMIT),
    staleTime: 0,
  })

  function handleLogout() {
    logout()
    queryClient.clear() // nada da conta anterior fica no cache
    navigate('/login', { replace: true })
  }

  const storiesById = new Map((stories.data ?? []).map((s) => [s.id, s]))
  // Histórias em andamento cuja história ainda existe na lista
  const inProgress = (recent.data ?? [])
    .filter((p) => !p.completed && storiesById.has(p.story_id))
    .slice(0, RECENT_LIMIT)

  const name = firstName(me.data?.name)

  return (
    <PageLayout wide>
      <header className="flex items-start justify-between gap-4 mb-8">
        <div>
          <h1 className="font-display text-3xl text-text-primary">{name ? `Olá, ${name}` : 'Olá'}</h1>
          <p className="text-text-muted mt-1">O que vamos ouvir hoje?</p>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          className="flex items-center gap-1.5 text-sm text-text-muted hover:text-text-primary transition-colors shrink-0"
        >
          <LogOut size={16} aria-hidden="true" />
          Sair
        </button>
      </header>

      <section aria-labelledby="continue-title" className="mb-10">
        <h2 id="continue-title" className="text-sm uppercase tracking-wider text-text-muted mb-3">
          Continuar ouvindo
        </h2>
        {recent.isPending || stories.isPending ? (
          <Skeleton label="Carregando suas histórias em andamento" />
        ) : recent.isError ? (
          <ErrorNotice message="Não foi possível carregar suas histórias em andamento." onRetry={() => recent.refetch()} />
        ) : inProgress.length === 0 ? (
          <p className={`${CARD} text-sm text-text-muted`}>
            Você ainda não começou nenhuma história. Escolha uma abaixo para ouvir.
          </p>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {inProgress.map((p) => (
              <ContinueCard key={p.story_id} progress={p} story={storiesById.get(p.story_id)!} />
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="stories-title">
        <h2 id="stories-title" className="text-sm uppercase tracking-wider text-text-muted mb-3">
          Histórias
        </h2>
        {stories.isPending ? (
          <Skeleton label="Carregando as histórias" />
        ) : stories.isError ? (
          <ErrorNotice message="Não foi possível carregar as histórias." onRetry={() => stories.refetch()} />
        ) : stories.data.length === 0 ? (
          <p className={`${CARD} text-sm text-text-muted`}>Ainda não há histórias disponíveis.</p>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {stories.data.map((story) => (
              <StoryCard key={story.id} story={story} />
            ))}
          </ul>
        )}
      </section>
    </PageLayout>
  )
}
