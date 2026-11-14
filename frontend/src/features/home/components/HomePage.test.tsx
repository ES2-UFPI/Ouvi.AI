import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { HomePage } from './HomePage'
import { useAuthStore } from '../../auth/store'
import * as progressApi from '../../progress/api'
import * as storiesApi from '../../stories/api'
import * as usersApi from '../../users/api'

vi.mock('../../progress/api')
vi.mock('../../stories/api')
vi.mock('../../users/api')

const historias = [
  { id: 1, title: 'A Raposa e as Uvas', description: 'Uma fábula clássica', segment_count: 12 },
  { id: 2, title: 'A Lebre e a Tartaruga', description: null, segment_count: 1 },
]

const progresso = (extra: Partial<progressApi.Progress> = {}): progressApi.Progress => ({
  story_id: 1,
  filter_id: 7,
  segment_position: 6,
  offset_ms: 2000,
  completed: false,
  client_time: '',
  updated_at: '',
  ...extra,
})

let client: QueryClient

function renderHome() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/login" element={<p>Tela de login</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.resetAllMocks()
  useAuthStore.setState({ token: 'tok', refreshToken: 'ref' })
  vi.mocked(usersApi.getMe).mockResolvedValue({ id: 1, name: 'Jeovando da Silva', email: 'j@x.com' })
  vi.mocked(storiesApi.listStories).mockResolvedValue(historias)
  vi.mocked(progressApi.listRecentProgress).mockResolvedValue([progresso()])
})

describe('HomePage', () => {
  it('mostra a saudação, as histórias em andamento e a lista de histórias', async () => {
    renderHome()

    expect(await screen.findByRole('heading', { name: 'Olá, Jeovando' })).toBeInTheDocument()
    const andamento = screen.getByRole('region', { name: 'Continuar ouvindo' })
    expect(within(andamento).getByText('A Raposa e as Uvas')).toBeInTheDocument()
    const lista = screen.getByRole('region', { name: 'Histórias' })
    expect(within(lista).getByText('A Raposa e as Uvas')).toBeInTheDocument()
    expect(within(lista).getByText('Uma fábula clássica')).toBeInTheDocument()
    expect(within(lista).getByText('12 frases')).toBeInTheDocument()
    expect(within(lista).getByText('1 frase')).toBeInTheDocument()
    expect(progressApi.listRecentProgress).toHaveBeenCalledWith(5)
  })

  it('mostra o progresso em barra e em texto ("frase 7 de 12")', async () => {
    renderHome()

    const barra = await screen.findByRole('progressbar', { name: 'Progresso em A Raposa e as Uvas' })
    expect(barra).toHaveAttribute('aria-valuenow', '58') // 7 de 12
    expect(barra).toHaveAttribute('aria-valuetext', 'frase 7 de 12')
    expect(screen.getByText('frase 7 de 12')).toBeInTheDocument()
  })

  it('"Continuar" leva ao player da história com o filtro salvo', async () => {
    renderHome()
    expect(await screen.findByRole('link', { name: 'Continuar' })).toHaveAttribute('href', '/player/1?filter=7')
  })

  it('sem filtro guardado no progresso, leva a escolher o filtro da história', async () => {
    vi.mocked(progressApi.listRecentProgress).mockResolvedValue([progresso({ filter_id: null })])
    renderHome()
    expect(await screen.findByRole('link', { name: 'Escolher filtro' })).toHaveAttribute('href', '/filter?story=1')
  })

  it('"Ouvir" leva ao filtro com a história já escolhida', async () => {
    renderHome()
    expect(await screen.findByRole('link', { name: 'Ouvir A Lebre e a Tartaruga' })).toHaveAttribute(
      'href',
      '/filter?story=2',
    )
  })

  it('não mostra histórias concluídas nem histórias que não existem mais', async () => {
    vi.mocked(progressApi.listRecentProgress).mockResolvedValue([
      progresso({ story_id: 2, completed: true }),
      progresso({ story_id: 99 }),
    ])
    renderHome()

    const andamento = await screen.findByRole('region', { name: 'Continuar ouvindo' })
    await waitFor(() => expect(within(andamento).getByText(/ainda não começou nenhuma história/)).toBeInTheDocument())
    expect(within(andamento).queryByRole('progressbar')).not.toBeInTheDocument()
  })

  it('sem histórias em andamento, convida a escolher uma', async () => {
    vi.mocked(progressApi.listRecentProgress).mockResolvedValue([])
    renderHome()
    expect(await screen.findByText(/Você ainda não começou nenhuma história/)).toBeInTheDocument()
  })

  it('sem histórias cadastradas, avisa', async () => {
    vi.mocked(storiesApi.listStories).mockResolvedValue([])
    renderHome()
    expect(await screen.findByText('Ainda não há histórias disponíveis.')).toBeInTheDocument()
  })

  it('enquanto carrega, mostra os indicadores de carregamento', () => {
    vi.mocked(storiesApi.listStories).mockReturnValue(new Promise(() => undefined))
    vi.mocked(progressApi.listRecentProgress).mockReturnValue(new Promise(() => undefined))
    renderHome()

    expect(screen.getByRole('status', { name: 'Carregando suas histórias em andamento' })).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Carregando as histórias' })).toBeInTheDocument()
  })

  it('erro ao carregar as histórias mostra o aviso e permite tentar de novo', async () => {
    vi.mocked(storiesApi.listStories).mockRejectedValueOnce(new Error('falhou'))
    renderHome()

    const aviso = await screen.findAllByRole('alert')
    expect(aviso.some((a) => a.textContent?.includes('Não foi possível carregar as histórias.'))).toBe(true)

    fireEvent.click(screen.getAllByRole('button', { name: 'Tentar de novo' })[0])
    expect(await screen.findByText('Uma fábula clássica')).toBeInTheDocument()
  })

  it('erro ao carregar o progresso não esconde a lista de histórias', async () => {
    vi.mocked(progressApi.listRecentProgress).mockRejectedValue(new Error('falhou'))
    renderHome()

    expect(await screen.findByText('Não foi possível carregar suas histórias em andamento.')).toBeInTheDocument()
    expect(screen.getByText('Uma fábula clássica')).toBeInTheDocument()
  })

  it('se não conseguir ler o nome, cumprimenta sem ele', async () => {
    vi.mocked(usersApi.getMe).mockRejectedValue(new Error('falhou'))
    renderHome()
    expect(await screen.findByRole('heading', { name: 'Olá' })).toBeInTheDocument()
    expect(await screen.findByText('Uma fábula clássica')).toBeInTheDocument()
  })

  it('"Sair" encerra a sessão, limpa o cache e volta ao login', async () => {
    renderHome()
    await screen.findByText('Uma fábula clássica')
    expect(client.getQueryCache().getAll().length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('button', { name: 'Sair' }))

    expect(await screen.findByText('Tela de login')).toBeInTheDocument()
    expect(useAuthStore.getState().token).toBeNull()
    expect(useAuthStore.getState().refreshToken).toBeNull()
    expect(client.getQueryCache().getAll()).toHaveLength(0)
  })
})
