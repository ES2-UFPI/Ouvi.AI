import { AxiosError } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { PlayerPage } from './PlayerPage'
import * as filtersApi from '../../filters/api'
import * as storiesApi from '../../stories/api'
import * as playerApi from '../api'

vi.mock('../../filters/api')
vi.mock('../../stories/api')
vi.mock('../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api')>()),
  getAudioUrl: vi.fn(),
}))

function erroHttp(status: number) {
  return new AxiosError('falhou', 'ERR_BAD_REQUEST', undefined, null, {
    status,
    data: {},
    statusText: '',
    headers: {},
    config: {} as never,
  })
}

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

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(storiesApi.listStories).mockResolvedValue([
    { id: 1, title: 'A Raposa e as Uvas', description: null },
  ])
  vi.mocked(filtersApi.getFilter).mockResolvedValue({
    id: 7,
    story_id: 1,
    rules: { base_language: 'pt', segment_types: ['phrasal_verbs'], density: 'high' },
    created_at: '',
    updated_at: '',
  })
})

describe('PlayerPage', () => {
  it('pede o áudio da história pela chave certa', async () => {
    vi.mocked(playerApi.getAudioUrl).mockResolvedValue({ url: 'http://api/audio/stream?x=1', expires_at: '' })
    renderPlayer()
    await screen.findByText('A Raposa e as Uvas')
    expect(playerApi.getAudioUrl).toHaveBeenCalledWith('stories/1/audio.wav')
  })

  it('mostra o player com o título da história e o áudio da URL assinada', async () => {
    vi.mocked(playerApi.getAudioUrl).mockResolvedValue({ url: 'http://api/audio/stream?x=1', expires_at: '' })
    const { container } = renderPlayer()

    expect(await screen.findByText('A Raposa e as Uvas')).toBeInTheDocument()
    expect(screen.getByLabelText('Reproduzir')).toBeInTheDocument()
    expect(container.querySelector('audio')).toHaveAttribute('src', 'http://api/audio/stream?x=1')
  })

  it('mostra o resumo do filtro escolhido', async () => {
    vi.mocked(playerApi.getAudioUrl).mockResolvedValue({ url: 'http://api/a', expires_at: '' })
    renderPlayer()
    expect(await screen.findByText('Base: Português')).toBeInTheDocument()
    expect(screen.getByText('Phrasal verbs')).toBeInTheDocument()
    expect(screen.getByText('Densidade alta')).toBeInTheDocument()
  })

  it('enquanto busca a URL, mostra o carregamento', () => {
    vi.mocked(playerApi.getAudioUrl).mockReturnValue(new Promise(() => {}))
    renderPlayer()
    expect(screen.getByRole('status')).toHaveTextContent('Carregando áudio')
  })

  it('história sem áudio (404) avisa que o áudio ainda não foi gerado', async () => {
    vi.mocked(playerApi.getAudioUrl).mockRejectedValue(erroHttp(404))
    renderPlayer()
    expect(await screen.findByRole('alert')).toHaveTextContent('O áudio desta história ainda não foi gerado.')
  })

  it('outro erro da API mostra uma mensagem para tentar de novo', async () => {
    vi.mocked(playerApi.getAudioUrl).mockRejectedValue(erroHttp(503))
    renderPlayer()
    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível obter o áudio agora')
  })

  it('id de história inválido mostra "História não encontrada" sem chamar a API de áudio', async () => {
    renderPlayer('/player/abc')
    expect(await screen.findByRole('alert')).toHaveTextContent('História não encontrada.')
    expect(playerApi.getAudioUrl).not.toHaveBeenCalled()
  })

  it('funciona sem filtro na URL (não mostra o resumo)', async () => {
    vi.mocked(playerApi.getAudioUrl).mockResolvedValue({ url: 'http://api/a', expires_at: '' })
    renderPlayer('/player/1')
    await screen.findByText('A Raposa e as Uvas')
    expect(filtersApi.getFilter).not.toHaveBeenCalled()
    expect(screen.queryByLabelText('Filtro escolhido')).not.toBeInTheDocument()
  })
})
