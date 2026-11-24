import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import { Headphones, LogOut, Upload } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../auth/store'
import { listRecentProgress, type Progress } from '../../progress/api'
import { importStory, listStories, type Story, type StoryImport } from '../../stories/api'
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
      {story.is_mine && (
        <span
          className="self-start text-[11px] uppercase tracking-wider rounded-full px-2 py-0.5 mb-2"
          style={{ backgroundColor: 'var(--color-accent-en)', color: 'var(--color-bg-deep)' }}
        >
          Sua história
        </span>
      )}
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

function importErrorMessage(error: unknown) {
  if (isAxiosError(error) && typeof error.response?.data?.detail === 'string') return error.response.data.detail
  return 'Não foi possível enviar o arquivo. Tente de novo.'
}

// US18: o usuário envia o próprio texto (inglês e português, frase a frase) para ouvir com os filtros
function UploadStoryCard() {
  const queryClient = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [result, setResult] = useState<StoryImport | null>(null)
  const [inputKey, setInputKey] = useState(0) // trocar a key limpa o campo de arquivo depois do envio
  const upload = useMutation({
    mutationFn: () => importStory(file!, title),
    onSuccess: (data) => {
      setResult(data)
      setFile(null)
      setTitle('')
      setInputKey((k) => k + 1)
      queryClient.invalidateQueries({ queryKey: ['stories'] })
    },
  })

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setResult(null)
    if (file) upload.mutate()
  }

  return (
    <section aria-labelledby="upload-title" className="mb-10">
      <h2 id="upload-title" className="text-sm uppercase tracking-wider text-text-muted mb-3">
        Enviar sua história
      </h2>
      <form onSubmit={handleSubmit} className={`${CARD} grid gap-3`}>
        <p className="text-sm text-text-muted">
          Envie um <strong>.txt</strong> com cada frase em inglês seguida da tradução em português (linha por linha) ou
          um <strong>.json</strong> no formato das histórias. Linhas <code>= termo -&gt; tradução</code> ajudam a
          trocar as palavras.
        </p>
        <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] items-end">
          <label className="text-sm text-text-muted grid gap-1">
            Arquivo
            <input
              key={inputKey}
              type="file"
              accept=".txt,.json"
              aria-label="Arquivo da história"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="text-sm text-text-primary file:mr-3 file:rounded-lg file:border-0 file:px-3 file:py-1.5 file:bg-bg-deep file:text-text-primary"
            />
          </label>
          <label className="text-sm text-text-muted grid gap-1">
            Título (opcional)
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Usa o do arquivo"
              className="rounded-lg bg-bg-deep border border-border-subtle px-3 py-1.5 text-text-primary"
            />
          </label>
          <button
            type="submit"
            disabled={!file || upload.isPending}
            className={`${PRIMARY_LINK} disabled:opacity-50`}
            style={{ backgroundColor: 'var(--color-accent-en)' }}
          >
            <Upload size={16} aria-hidden="true" />
            {upload.isPending ? 'Enviando e anotando...' : 'Enviar'}
          </button>
        </div>
        {upload.isError && (
          <p role="alert" className="text-sm" style={{ color: 'var(--color-accent-pt)' }}>
            {importErrorMessage(upload.error)}
          </p>
        )}
        {result && (
          <p role="status" className="text-sm text-text-primary">
            &ldquo;{result.story.title}&rdquo; criada: {result.story.segment_count} frases, {result.annotations} trechos
            encontrados ({result.aligned} com tradução).{' '}
            <Link to={`/filter?story=${result.story.id}`} className="underline">
              Ouvir agora
            </Link>
          </p>
        )}
      </form>
    </section>
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

      <UploadStoryCard />

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
