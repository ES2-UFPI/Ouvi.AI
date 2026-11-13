import { AxiosError } from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { PlayerPage } from './PlayerPage'
import * as filtersApi from '../../filters/api'
import * as storiesApi from '../../stories/api'
import * as playerApi from '../api'
import * as progressApi from '../../progress/api'
import type { AudioGenerationStatus, GenerationState } from '../api'

vi.mock('../../filters/api')
vi.mock('../../stories/api')
vi.mock('../api')
vi.mock('../../progress/api')

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
    { id: 1, title: 'A Raposa e as Uvas', description: null, segment_count: 3 },
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
  vi.mocked(progressApi.getProgress).mockResolvedValue(null)
  vi.mocked(progressApi.saveProgress).mockResolvedValue({} as never)
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

  it('ao pausar, guarda a posição da frase sem o usuário perceber', async () => {
    vi.mocked(playerApi.requestStoryAudio).mockResolvedValue(statusDe('ready', ['ready', 'ready']))
    const { container } = renderPlayer()
    await screen.findByLabelText('Reproduzir')
    await act(async () => {}) // o player liga os ouvintes do <audio> num efeito: espera ele rodar
    const audio = audioDe(container)

    fireEvent(audio, new Event('play'))
    audio.currentTime = 1.5
    fireEvent(audio, new Event('timeupdate'))
    fireEvent(audio, new Event('pause'))

    await vi.waitFor(() =>
      expect(progressApi.saveProgress).toHaveBeenCalledWith(1, {
        segment_position: 0,
        offset_ms: 1500,
        filter_id: 7,
        completed: false,
      }),
    )
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('uma falha ao salvar o progresso não interrompe o áudio nem mostra erro', async () => {
    vi.mocked(playerApi.requestStoryAudio).mockResolvedValue(statusDe('ready', ['ready']))
    vi.mocked(progressApi.saveProgress).mockRejectedValue(new Error('sem rede'))
    const { container } = renderPlayer()
    await screen.findByLabelText('Reproduzir')
    await act(async () => {})

    fireEvent(audioDe(container), new Event('play'))
    fireEvent(audioDe(container), new Event('pause'))

    await vi.waitFor(() => expect(progressApi.saveProgress).toHaveBeenCalled())
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(audioDe(container)).toHaveAttribute('src', urlDaFrase(1))
  })

  it('ao terminar a história, marca o progresso como concluído na última frase', async () => {
    vi.mocked(playerApi.requestStoryAudio).mockResolvedValue(statusDe('ready', ['ready', 'ready']))
    const { container } = renderPlayer()
    await screen.findByLabelText('Reproduzir')

    fireEvent(audioDe(container), new Event('ended'))
    await screen.findByText('Frase 2 de 2')
    fireEvent(audioDe(container), new Event('ended'))

    await vi.waitFor(() =>
      expect(progressApi.saveProgress).toHaveBeenCalledWith(1, {
        segment_position: 1,
        offset_ms: 0,
        filter_id: 7,
        completed: true,
      }),
    )
  })

  // ---------- retomar de onde parou (#98) ----------

  const progressoSalvo = (extra: Partial<progressApi.Progress> = {}): progressApi.Progress => ({
    story_id: 1,
    filter_id: 7,
    segment_position: 2,
    offset_ms: 3000,
    completed: false,
    client_time: '',
    updated_at: '',
    ...extra,
  })

  it('com progresso salvo, mostra o cartão e não toca nem gera nada antes da escolha', async () => {
    vi.mocked(playerApi.requestStoryAudio).mockResolvedValue(statusDe('ready', ['ready', 'ready', 'ready']))
    vi.mocked(progressApi.getProgress).mockResolvedValue(progressoSalvo())
    const { container } = renderPlayer()

    const cartao = await screen.findByRole('region', { name: 'A Raposa e as Uvas' })
    expect(cartao).toHaveTextContent('Você parou na frase 3 de 3.')
    expect(cartao).toHaveTextContent('Cerca de 0:03 dentro da frase.')
    expect(screen.getByRole('button', { name: 'Continuar' })).toHaveFocus()
    expect(container.querySelector('audio')).toBeNull()
    expect(playerApi.getSegmentAudio).not.toHaveBeenCalled()
    expect(progressApi.saveProgress).not.toHaveBeenCalled()
  })

  it('"Continuar" começa exatamente na frase salva e no ponto salvo', async () => {
    vi.mocked(playerApi.requestStoryAudio).mockResolvedValue(statusDe('ready', ['ready', 'ready', 'ready']))
    vi.mocked(progressApi.getProgress).mockResolvedValue(progressoSalvo())
    const { container } = renderPlayer()

    fireEvent.click(await screen.findByRole('button', { name: 'Continuar' }))

    expect(await screen.findByText('Frase 3 de 3')).toBeInTheDocument()
    const audio = audioDe(container)
    expect(audio).toHaveAttribute('src', urlDaFrase(3))
    expect(audio).toHaveAttribute('autoplay')
    expect(progressApi.deleteProgress).not.toHaveBeenCalled()

    // O ponto salvo é aplicado quando a faixa tem duração (o ouvinte é ligado num efeito: espera ele rodar)
    await act(async () => {})
    Object.defineProperty(audio, 'duration', { configurable: true, value: 10 })
    fireEvent(audio, new Event('loadedmetadata'))
    expect(audio.currentTime).toBe(3)
  })

  it('"Recomeçar" apaga o progresso e toca do início', async () => {
    vi.mocked(playerApi.requestStoryAudio).mockResolvedValue(statusDe('ready', ['ready', 'ready', 'ready']))
    vi.mocked(progressApi.getProgress).mockResolvedValue(progressoSalvo())
    vi.mocked(progressApi.deleteProgress).mockResolvedValue(undefined)
    const { container } = renderPlayer()

    fireEvent.click(await screen.findByRole('button', { name: 'Recomeçar' }))

    expect(await screen.findByText('Frase 1 de 3')).toBeInTheDocument()
    expect(audioDe(container)).toHaveAttribute('src', urlDaFrase(1))
    expect(progressApi.deleteProgress).toHaveBeenCalledWith(1)
  })

  it('se não foi possível apagar o progresso, recomeça mesmo assim', async () => {
    vi.mocked(playerApi.requestStoryAudio).mockResolvedValue(statusDe('ready', ['ready', 'ready', 'ready']))
    vi.mocked(progressApi.getProgress).mockResolvedValue(progressoSalvo())
    vi.mocked(progressApi.deleteProgress).mockRejectedValue(new Error('sem rede'))
    renderPlayer()

    fireEvent.click(await screen.findByRole('button', { name: 'Recomeçar' }))

    expect(await screen.findByText('Frase 1 de 3')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it.each([
    ['sem progresso', null],
    ['com a história concluída', progressoSalvo({ completed: true, segment_position: 2 })],
    ['com o progresso no começo da primeira frase', progressoSalvo({ segment_position: 0, offset_ms: 200 })],
  ])('%s, começa do início sem mostrar o cartão', async (_nome, salvo) => {
    vi.mocked(playerApi.requestStoryAudio).mockResolvedValue(statusDe('ready', ['ready', 'ready', 'ready']))
    vi.mocked(progressApi.getProgress).mockResolvedValue(salvo)
    const { container } = renderPlayer()

    expect(await screen.findByText('Frase 1 de 3')).toBeInTheDocument()
    expect(audioDe(container)).toHaveAttribute('src', urlDaFrase(1))
    expect(screen.queryByRole('button', { name: 'Continuar' })).not.toBeInTheDocument()
  })

  it('se não conseguir ler o progresso, começa do início sem mostrar erro', async () => {
    vi.mocked(playerApi.requestStoryAudio).mockResolvedValue(statusDe('ready', ['ready']))
    vi.mocked(progressApi.getProgress).mockRejectedValue(erroHttp(500))
    renderPlayer()

    expect(await screen.findByText('Frase 1 de 1')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('se a frase salva ainda não foi gerada, espera e toca quando ela ficar pronta', async () => {
    vi.mocked(playerApi.requestStoryAudio).mockResolvedValue(statusDe('generating', ['ready', 'ready', 'generating']))
    vi.mocked(playerApi.getStoryAudioStatus).mockResolvedValue(statusDe('ready', ['ready', 'ready', 'ready']))
    vi.mocked(progressApi.getProgress).mockResolvedValue(progressoSalvo())
    const { container } = renderPlayer()

    fireEvent.click(await screen.findByRole('button', { name: 'Continuar' }))
    expect(await screen.findByText('Gerando o áudio da próxima frase...')).toBeInTheDocument()

    await act(() => vi.advanceTimersByTimeAsync(1500))
    await vi.waitFor(() => expect(audioDe(container)).toHaveAttribute('src', urlDaFrase(3)))
  })

  it('depois de continuar, o progresso volta a ser salvo', async () => {
    vi.mocked(playerApi.requestStoryAudio).mockResolvedValue(statusDe('ready', ['ready', 'ready', 'ready']))
    vi.mocked(progressApi.getProgress).mockResolvedValue(progressoSalvo())
    const { container } = renderPlayer()
    fireEvent.click(await screen.findByRole('button', { name: 'Continuar' }))
    await screen.findByLabelText('Reproduzir')
    await act(async () => {})

    fireEvent(audioDe(container), new Event('play'))
    fireEvent(audioDe(container), new Event('pause'))

    await vi.waitFor(() =>
      expect(progressApi.saveProgress).toHaveBeenCalledWith(1, expect.objectContaining({ segment_position: 2 })),
    )
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

  describe('faixa de densidade (Cenário C)', () => {
    const PERFIL = [
      { segment_id: 1, position: 0, candidates: 1, swapped: 0, target: 0.2 },
      { segment_id: 2, position: 1, candidates: 1, swapped: 1, target: 0.36 },
      { segment_id: 3, position: 2, candidates: 1, swapped: 1, target: 0.52 },
    ]

    beforeEach(() => {
      vi.mocked(filtersApi.getFilter).mockResolvedValue({
        id: 7,
        story_id: 1,
        rules: { base_language: 'pt', segment_types: ['advanced_vocabulary'], density: 'high', progression: 'increasing' },
        created_at: '',
        updated_at: '',
      })
      vi.mocked(storiesApi.getStoryPreview).mockResolvedValue({
        story: { id: 1, title: 'A Raposa e as Uvas', language: 'en' },
        rules: { base_language: 'pt', segment_types: ['advanced_vocabulary'], density: 'high', progression: 'increasing' },
        totals: { segments: 3, candidates: 3, swapped: 2 },
        density_profile: PERFIL,
        segments: [],
      })
      vi.mocked(playerApi.requestStoryAudio).mockResolvedValue(statusDe('ready', ['ready', 'ready', 'ready']))
    })

    it('mostra uma coluna por frase, destaca a atual e o texto acompanha a frase', async () => {
      const { container } = renderPlayer()
      await screen.findByLabelText('Reproduzir')

      expect(screen.getByText('Densidade final alta')).toBeInTheDocument()
      expect(screen.getByText('Progressão crescente')).toBeInTheDocument()
      const faixa = await screen.findByRole('region', { name: 'Densidade de inglês por frase' })
      expect(storiesApi.getStoryPreview).toHaveBeenCalledWith(1, 7)
      const colunas = screen.getAllByRole('button', { name: /^Frase \d: / })
      expect(colunas).toHaveLength(3)
      expect(colunas[0]).toHaveAttribute('aria-current', 'true')
      expect(faixa).toHaveTextContent('Inglês nesta parte: 20%')

      fireEvent(audioDe(container), new Event('ended'))
      expect(await screen.findByText('Inglês nesta parte: 36%')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /^Frase 2: 36% de inglês, 1 palavra em inglês \(tocando agora\)/ })).toHaveAttribute(
        'aria-current',
        'true',
      )
    })

    it('clicar numa coluna leva o player à frase correspondente', async () => {
      renderPlayer()
      await screen.findByLabelText('Reproduzir')

      fireEvent.click(await screen.findByRole('button', { name: /^Frase 3: / }))

      expect(await screen.findByText('Frase 3 de 3')).toBeInTheDocument()
      expect(screen.getByText('Inglês nesta parte: 52%')).toBeInTheDocument()
      expect(screen.getByText('Frase 3.').closest('p')).toHaveAttribute('aria-current', 'true')
    })

    it('tem alternativa em texto para leitores de tela', async () => {
      renderPlayer()
      const faixa = await screen.findByRole('region', { name: 'Densidade de inglês por frase' })
      expect(faixa).toHaveTextContent(
        'O inglês começa em 20% e sobe até 52% no final da história. 2 de 3 palavras de vocabulário avançado são faladas em inglês.',
      )
    })
  })

  it('a faixa de densidade não aparece nos filtros de densidade fixa', async () => {
    vi.mocked(playerApi.requestStoryAudio).mockResolvedValue(statusDe('ready', ['ready']))
    renderPlayer()
    await screen.findByLabelText('Reproduzir')
    expect(screen.queryByRole('region', { name: 'Densidade de inglês por frase' })).not.toBeInTheDocument()
    expect(storiesApi.getStoryPreview).not.toHaveBeenCalled()
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
