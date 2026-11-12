import { AxiosError } from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { PlayerPage } from './PlayerPage'
import * as filtersApi from '../../filters/api'
import * as storiesApi from '../../stories/api'
import * as playerApi from '../api'
import type { AudioGenerationStatus, GenerationState } from '../api'

vi.mock('../../filters/api')
vi.mock('../../stories/api')
vi.mock('../api')

function erroHttp(status: number) {
  return new AxiosError('falhou', 'ERR_BAD_REQUEST', undefined, null, {
    status,
    data: {},
    statusText: '',
    headers: {},
    config: {} as never,
  })
}

// Monta o status da geração a partir do estado de cada frase (ids 1, 2, 3... nas posições 0, 1, 2...)
function statusDe(state: GenerationState, frases: GenerationState[]): AudioGenerationStatus {
  return {
    story_id: 1,
    filter_id: 7,
    state,
    total: frases.length,
    ready: frases.filter((f) => f === 'ready').length,
    failed: frases.filter((f) => f === 'failed').length,
    segments: frases.map((status, i) => ({
      segment_id: i + 1,
      position: i,
      status,
      duration_ms: status === 'ready' ? 1000 : null,
      error: status === 'failed' ? 'TTS falhou' : null,
    })),
  }
}

const urlDaFrase = (id: number) => `http://api/audio/stream?frase=${id}`

function renderPlayer(rota = '/player/1?filter=7') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[rota]}>
        <Routes>
          <Route path="/player/:storyId" element={<PlayerPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const audioDe = (container: HTMLElement) => container.querySelector('audio')!

beforeEach(() => {
  // Só o setTimeout (o do polling) é falso, e ainda anda sozinho: dá para pular o intervalo sem travar o findBy
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'], shouldAdvanceTime: true })
  vi.resetAllMocks()
  vi.mocked(storiesApi.listStories).mockResolvedValue([
    { id: 1, title: 'A Raposa e as Uvas', description: null },
  ])
  vi.mocked(storiesApi.getStorySegments).mockResolvedValue({
    story: { id: 1, title: 'A Raposa e as Uvas', language: 'en' },
    segments: [1, 2, 3].map((id) => ({
      id,
      position: id - 1,
      text_en: `Sentence ${id}.`,
      text_pt: `Frase ${id}.`,
      annotations: [],
    })),
  })
  vi.mocked(filtersApi.getFilter).mockResolvedValue({
    id: 7,
    story_id: 1,
    rules: { base_language: 'pt', segment_types: ['phrasal_verbs'], density: 'high' },
    created_at: '',
    updated_at: '',
  })
  vi.mocked(playerApi.getSegmentAudio).mockImplementation(async (segmentId) => ({
    url: urlDaFrase(segmentId),
    expires_at: '',
    segment_id: segmentId,
    duration_ms: 1000,
    format: 'wav',
  }))
})

afterEach(() => {
  vi.useRealTimers()
})

describe('PlayerPage', () => {
  it('pede a geração do áudio da história com o filtro da URL', async () => {
    vi.mocked(playerApi.requestStoryAudio).mockResolvedValue(statusDe('ready', ['ready']))
    renderPlayer()
    await screen.findByText('A Raposa e as Uvas')
    expect(playerApi.requestStoryAudio).toHaveBeenCalledWith(1, 7)
  })

  it('mostra o progresso da geração e começa a tocar assim que a primeira frase fica pronta', async () => {
    vi.mocked(playerApi.requestStoryAudio).mockResolvedValue(statusDe('generating', ['generating', 'pending']))
    vi.mocked(playerApi.getStoryAudioStatus).mockResolvedValue(statusDe('generating', ['ready', 'generating']))
    const { container } = renderPlayer()

    expect(await screen.findByRole('status')).toHaveTextContent('Gerando áudio: 0/2 frases')
    expect(playerApi.getSegmentAudio).not.toHaveBeenCalled()

    await act(() => vi.advanceTimersByTimeAsync(1500))

    expect(await screen.findByLabelText('Reproduzir')).toBeInTheDocument()
    expect(audioDe(container)).toHaveAttribute('src', urlDaFrase(1))
    expect(audioDe(container)).toHaveAttribute('autoplay')
    expect(playerApi.getSegmentAudio).toHaveBeenCalledWith(1, 7)
    expect(screen.getByText('Frase 1 de 2 · Gerando áudio: 1/2 frases')).toBeInTheDocument()
  })

  it('ao terminar uma frase, toca a próxima', async () => {
    vi.mocked(playerApi.requestStoryAudio).mockResolvedValue(statusDe('ready', ['ready', 'ready']))
    const { container } = renderPlayer()
    await screen.findByLabelText('Reproduzir')
    expect(audioDe(container)).toHaveAttribute('src', urlDaFrase(1))

    fireEvent(audioDe(container), new Event('ended'))

    expect(await screen.findByText('Frase 2 de 2')).toBeInTheDocument()
    expect(audioDe(container)).toHaveAttribute('src', urlDaFrase(2))
  })

  it('se a próxima frase ainda está sendo gerada, espera e continua quando ela fica pronta', async () => {
    vi.mocked(playerApi.requestStoryAudio).mockResolvedValue(statusDe('generating', ['ready', 'generating']))
    vi.mocked(playerApi.getStoryAudioStatus).mockResolvedValue(statusDe('generating', ['ready', 'generating']))
    const { container } = renderPlayer()
    await screen.findByLabelText('Reproduzir')

    fireEvent(audioDe(container), new Event('ended'))

    expect(await screen.findByText('Gerando o áudio da próxima frase...')).toBeInTheDocument()
    expect(audioDe(container)).not.toHaveAttribute('src')

    vi.mocked(playerApi.getStoryAudioStatus).mockResolvedValue(statusDe('ready', ['ready', 'ready']))
    await act(() => vi.advanceTimersByTimeAsync(1500))

    expect(await screen.findByText('Frase 2 de 2')).toBeInTheDocument()
    expect(audioDe(container)).toHaveAttribute('src', urlDaFrase(2))
    expect(screen.queryByText('Gerando o áudio da próxima frase...')).not.toBeInTheDocument()
  })

  it('pula as frases que falharam, com um aviso discreto', async () => {
    vi.mocked(playerApi.requestStoryAudio).mockResolvedValue(statusDe('failed', ['ready', 'failed', 'ready']))
    const { container } = renderPlayer()
    await screen.findByLabelText('Reproduzir')
    expect(screen.getByText('1 frase não pôde ser gerada e foi pulada.')).toBeInTheDocument()

    fireEvent(audioDe(container), new Event('ended'))

    expect(await screen.findByText('Frase 3 de 3')).toBeInTheDocument()
    expect(audioDe(container)).toHaveAttribute('src', urlDaFrase(3))
    expect(playerApi.getSegmentAudio).not.toHaveBeenCalledWith(2, 7)
  })

  it('para o polling quando a geração termina e ao sair da página', async () => {
    vi.mocked(playerApi.requestStoryAudio).mockResolvedValue(statusDe('generating', ['generating']))
    vi.mocked(playerApi.getStoryAudioStatus).mockResolvedValue(statusDe('generating', ['generating']))
    const { unmount } = renderPlayer()
    await screen.findByRole('status')

    await act(() => vi.advanceTimersByTimeAsync(1500))
    expect(playerApi.getStoryAudioStatus).toHaveBeenCalledTimes(1)
    unmount()
    await act(() => vi.advanceTimersByTimeAsync(5000))
    expect(playerApi.getStoryAudioStatus).toHaveBeenCalledTimes(1)
  })

  it('destaca no texto a frase que está tocando', async () => {
    vi.mocked(playerApi.requestStoryAudio).mockResolvedValue(statusDe('ready', ['ready', 'ready', 'ready']))
    const { container } = renderPlayer()
    await screen.findByLabelText('Reproduzir')
    expect((await screen.findByText('Frase 1.')).closest('p')).toHaveAttribute('aria-current', 'true')

    fireEvent(audioDe(container), new Event('ended'))
    await screen.findByText('Frase 2 de 3')
    expect(screen.getByText('Frase 2.').closest('p')).toHaveAttribute('aria-current', 'true')
    expect(screen.getByText('Frase 1.').closest('p')).not.toHaveAttribute('aria-current')
  })

  it('mostra o resumo do filtro escolhido', async () => {
    vi.mocked(playerApi.requestStoryAudio).mockResolvedValue(statusDe('ready', ['ready']))
    renderPlayer()
    expect(await screen.findByText('Base: Português')).toBeInTheDocument()
    expect(screen.getByText('Phrasal verbs')).toBeInTheDocument()
    expect(screen.getByText('Densidade alta')).toBeInTheDocument()
  })

  it('enquanto pede a geração, mostra que está preparando o áudio', () => {
    vi.mocked(playerApi.requestStoryAudio).mockReturnValue(new Promise(() => {}))
    renderPlayer()
    expect(screen.getByRole('status')).toHaveTextContent('Preparando o áudio')
  })

  it('filtro inexistente (404) mostra o erro', async () => {
    vi.mocked(playerApi.requestStoryAudio).mockRejectedValue(erroHttp(404))
    renderPlayer()
    expect(await screen.findByRole('alert')).toHaveTextContent('História ou filtro não encontrado.')
  })

  it('outro erro da API mostra uma mensagem para tentar de novo', async () => {
    vi.mocked(playerApi.requestStoryAudio).mockRejectedValue(erroHttp(503))
    renderPlayer()
    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível gerar o áudio agora')
  })

  it('id de história inválido mostra "História não encontrada" sem chamar a API de áudio', async () => {
    renderPlayer('/player/abc?filter=7')
    expect(await screen.findByRole('alert')).toHaveTextContent('História não encontrada.')
    expect(playerApi.requestStoryAudio).not.toHaveBeenCalled()
  })

  it('sem filtro na URL, pede para escolher um em vez de gerar o áudio', async () => {
    renderPlayer('/player/1')
    expect(await screen.findByRole('alert')).toHaveTextContent('Escolha um filtro de audição')
    expect(screen.getByRole('link', { name: 'Escolher filtro' })).toHaveAttribute('href', '/filter')
    expect(playerApi.requestStoryAudio).not.toHaveBeenCalled()
    expect(filtersApi.getFilter).not.toHaveBeenCalled()
  })
})
