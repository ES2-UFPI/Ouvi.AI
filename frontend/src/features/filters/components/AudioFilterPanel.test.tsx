import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AxiosError, AxiosHeaders } from 'axios'
import { AudioFilterPanel } from './AudioFilterPanel'
import * as filtersApi from '../api'
import * as storiesApi from '../../stories/api'

vi.mock('../api')
vi.mock('../../stories/api')

const STORIES = [
  { id: 1, title: 'A Raposa e as Uvas', description: null, segment_count: 3 },
  { id: 2, title: 'A Lebre e a Tartaruga', description: null, segment_count: 3 },
]

const saved = (overrides = {}) => ({
  id: 7,
  story_id: 1,
  rules: { base_language: 'pt' as const, segment_types: ['phrasal_verbs' as const], density: 'high' as const },
  created_at: '',
  updated_at: '',
  ...overrides,
})

function renderPanel(rota = '/filter') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[rota]}>
        <AudioFilterPanel />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(storiesApi.listStories).mockResolvedValue(STORIES)
  vi.mocked(filtersApi.listFilters).mockResolvedValue([])
  vi.mocked(filtersApi.getFilterOptions).mockResolvedValue(OPTIONS)
  vi.mocked(storiesApi.getStoryPreview).mockResolvedValue(PREVIEW)
})

// Resposta de GET /filters/options (tabela de combinações do backend)
const OPTIONS = {
  scenarios: [
    {
      base_language: 'pt' as const,
      segment_types: ['phrasal_verbs' as const],
      word_levels: [],
      progressions: ['fixed' as const],
      description: 'Cenário A',
    },
    {
      base_language: 'en' as const,
      segment_types: ['difficult_words' as const],
      word_levels: ['intermediate' as const, 'advanced' as const],
      progressions: ['fixed' as const],
      description: 'Cenário B',
    },
    {
      base_language: 'pt' as const,
      segment_types: ['advanced_vocabulary' as const],
      word_levels: [],
      progressions: ['increasing' as const],
      description: 'Cenário C',
    },
  ],
  densities: ['low' as const, 'medium' as const, 'high' as const],
  word_levels: ['intermediate' as const, 'advanced' as const],
  progressions: ['fixed' as const, 'increasing' as const],
}

const SAVED_C = {
  base_language: 'pt' as const,
  segment_types: ['advanced_vocabulary' as const],
  density: 'high' as const,
  progression: 'increasing' as const,
}

// Prévia (GET /stories/{id}/preview) de uma história com trocas no começo e no fim
const PREVIEW = {
  story: { id: 1, title: 'A Raposa e as Uvas', language: 'en' },
  rules: SAVED_C,
  totals: { segments: 3, candidates: 3, swapped: 2 },
  density_profile: [],
  segments: [
    { id: 1, position: 0, text: 'A raposa faminta.', swaps: [swap(9, 16, 'faminta', 'famished', 11)] },
    { id: 2, position: 1, text: 'Nada aconteceu.', swaps: [] },
    { id: 3, position: 2, text: 'Ela ficou descontente.', swaps: [swap(10, 21, 'descontente', 'disgruntled', 12)] },
  ],
}

function swap(start: number, end: number, text: string, spoken: string, annotation_id: number) {
  return { start, end, text, spoken, lang: 'en-US', annotation_id }
}

function axios422(msg: string) {
  return new AxiosError('422', 'ERR_BAD_REQUEST', undefined, undefined, {
    status: 422,
    statusText: 'Unprocessable Entity',
    data: { detail: [{ loc: ['body', 'rules'], msg: `Value error, ${msg}`, type: 'value_error' }] },
    headers: {},
    config: { headers: new AxiosHeaders() },
  })
}

describe('AudioFilterPanel', () => {
  it('tem um caminho de volta para a tela inicial', async () => {
    renderPanel()
    expect(await screen.findByRole('link', { name: 'Início' })).toHaveAttribute('href', '/')
  })

  it('vindo da tela inicial (?story=2), a história já chega escolhida', async () => {
    renderPanel('/filter?story=2')
    await screen.findByRole('option', { name: 'A Lebre e a Tartaruga' })
    expect(screen.getByRole('combobox', { name: /história/i })).toHaveValue('2')
  })

  it('com um ?story= inválido, escolhe a primeira história', async () => {
    renderPanel('/filter?story=abc')
    await screen.findByRole('option', { name: 'A Raposa e as Uvas' })
    expect(screen.getByRole('combobox', { name: /história/i })).toHaveValue('1')
  })

  it('lista as histórias e as opções de idioma base e densidade', async () => {
    renderPanel()
    expect(await screen.findByRole('option', { name: 'A Raposa e as Uvas' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'A Lebre e a Tartaruga' })).toBeInTheDocument()
    expect(screen.getByLabelText(/Português/)).toBeInTheDocument()
    expect(screen.getByLabelText(/English/)).toBeInTheDocument()
    expect(screen.getByText('Escolha o idioma base para ver os tipos de trecho.')).toBeInTheDocument()
    for (const label of ['Baixa', 'Média', 'Alta']) expect(screen.getByLabelText(label)).toBeInTheDocument()
  })

  it('português mostra phrasal verbs e vocabulário avançado (Cenários A e C), sem o campo de nível', async () => {
    const user = userEvent.setup()
    renderPanel()
    await waitFor(() => expect(filtersApi.getFilterOptions).toHaveBeenCalled())
    // A e C são dois cenários com a mesma base: o idioma aparece uma vez só
    expect(await screen.findAllByLabelText(/Português/)).toHaveLength(1)
    await user.click(screen.getByLabelText(/Português/))
    expect(screen.getByLabelText('Phrasal verbs')).toBeInTheDocument()
    expect(screen.getByLabelText('Vocabulário avançado')).toBeInTheDocument()
    expect(screen.getByText(/as palavras raras são faladas em inglês/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Palavras difíceis')).not.toBeInTheDocument()
    expect(screen.queryByText('Nível das palavras')).not.toBeInTheDocument()
  })

  it('inglês mostra palavras difíceis e o campo de nível', async () => {
    const user = userEvent.setup()
    renderPanel()
    await user.click(await screen.findByLabelText(/English/))
    expect(screen.getByLabelText('Palavras difíceis')).toBeInTheDocument()
    expect(screen.queryByLabelText('Phrasal verbs')).not.toBeInTheDocument()
    expect(screen.getByText('Nível das palavras')).toBeInTheDocument()
    expect(screen.getByLabelText('Intermediário')).toBeInTheDocument()
    expect(screen.getByLabelText('Avançado')).toBeInTheDocument()
  })

  it('não deixa salvar sem idioma base, sem tipo de trecho ou sem nível', async () => {
    const user = userEvent.setup()
    renderPanel()
    const button = await screen.findByRole('button', { name: 'Salvar filtro' })
    expect(button).toBeDisabled()

    await user.click(screen.getByLabelText(/English/))
    expect(button).toBeDisabled() // falta o tipo de trecho

    await user.click(screen.getByLabelText('Palavras difíceis'))
    expect(button).toBeDisabled() // falta o nível

    await user.click(screen.getByLabelText('Avançado'))
    expect(button).toBeEnabled()

    await user.click(screen.getByLabelText('Palavras difíceis')) // desmarcou: falta o tipo de novo
    expect(button).toBeDisabled()
  })

  it('cria o filtro do Cenário B com o nível', async () => {
    const user = userEvent.setup()
    vi.mocked(filtersApi.createFilter).mockResolvedValue(saved())
    renderPanel()
    await screen.findByRole('option', { name: 'A Raposa e as Uvas' })

    await user.click(screen.getByLabelText(/English/))
    await user.click(screen.getByLabelText('Palavras difíceis'))
    await user.click(screen.getByLabelText('Intermediário'))
    await user.click(screen.getByLabelText('Baixa'))
    await user.click(screen.getByRole('button', { name: 'Salvar filtro' }))

    await waitFor(() =>
      expect(filtersApi.createFilter).toHaveBeenCalledWith({
        story_id: 1,
        rules: {
          base_language: 'en',
          segment_types: ['difficult_words'],
          density: 'low',
          word_level: 'intermediate',
        },
      }),
    )
  })

  it('trocar o idioma base limpa o tipo e o nível escolhidos', async () => {
    const user = userEvent.setup()
    renderPanel()
    await user.click(await screen.findByLabelText(/English/))
    await user.click(screen.getByLabelText('Palavras difíceis'))
    await user.click(screen.getByLabelText('Avançado'))
    await user.click(screen.getByLabelText(/Português/))

    expect(screen.queryByText('Nível das palavras')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Phrasal verbs')).not.toBeChecked()
    expect(screen.getByRole('button', { name: 'Salvar filtro' })).toBeDisabled()
  })

  it('reaparece preenchido com o nível salvo', async () => {
    vi.mocked(filtersApi.listFilters).mockResolvedValue([
      saved({
        rules: { base_language: 'en', segment_types: ['difficult_words'], density: 'medium', word_level: 'advanced' },
      }),
    ])
    renderPanel()

    await waitFor(() => expect(screen.getByLabelText(/English/)).toBeChecked())
    expect(screen.getByLabelText('Palavras difíceis')).toBeChecked()
    expect(screen.getByLabelText('Avançado')).toBeChecked()
    expect(screen.getByLabelText('Média')).toBeChecked()
    expect(screen.getByRole('link', { name: 'Ouvir' })).toHaveAttribute('href', '/player/1?filter=7')
  })

  it('mostra a mensagem da API quando a combinação é recusada (422)', async () => {
    const user = userEvent.setup()
    vi.mocked(filtersApi.createFilter).mockRejectedValue(
      axios422("word_level é obrigatório com idioma base 'en' (intermediate, advanced)"),
    )
    renderPanel()
    await user.click(await screen.findByLabelText(/English/))
    await user.click(screen.getByLabelText('Palavras difíceis'))
    await user.click(screen.getByLabelText('Avançado'))
    await user.click(screen.getByRole('button', { name: 'Salvar filtro' }))

    const alerta = await screen.findByRole('alert')
    expect(alerta).toHaveTextContent("Filtro inválido: word_level é obrigatório com idioma base 'en'")
    expect(alerta).not.toHaveTextContent('Value error')
  })

  it('usa as combinações conhecidas quando /filters/options falha', async () => {
    const user = userEvent.setup()
    vi.mocked(filtersApi.getFilterOptions).mockRejectedValue(new Error('falhou'))
    renderPanel()
    await user.click(await screen.findByLabelText(/English/))
    expect(screen.getByLabelText('Palavras difíceis')).toBeInTheDocument()
    expect(screen.getByLabelText('Intermediário')).toBeInTheDocument()
  })

  it('cria o filtro com os valores escolhidos', async () => {
    const user = userEvent.setup()
    vi.mocked(filtersApi.createFilter).mockResolvedValue(saved())
    renderPanel()
    await screen.findByRole('option', { name: 'A Raposa e as Uvas' })

    await user.click(screen.getByLabelText(/Português/))
    await user.click(screen.getByLabelText('Phrasal verbs'))
    await user.click(screen.getByLabelText('Alta'))
    await user.click(screen.getByRole('button', { name: 'Salvar filtro' }))

    await waitFor(() =>
      expect(filtersApi.createFilter).toHaveBeenCalledWith({
        story_id: 1,
        rules: { base_language: 'pt', segment_types: ['phrasal_verbs'], density: 'high' },
      }),
    )
  })

  it('reaparece preenchido quando a história já tem filtro salvo e permite ouvir', async () => {
    vi.mocked(filtersApi.listFilters).mockResolvedValue([saved()])
    renderPanel()

    await waitFor(() => expect(screen.getByLabelText(/Português/)).toBeChecked())
    expect(screen.getByLabelText('Phrasal verbs')).toBeChecked()
    expect(screen.getByLabelText('Alta')).toBeChecked()
    expect(screen.getByRole('link', { name: 'Ouvir' })).toHaveAttribute('href', '/player/1?filter=7')
  })

  it('atualiza (e não cria outro) quando a história já tem filtro', async () => {
    const user = userEvent.setup()
    vi.mocked(filtersApi.listFilters).mockResolvedValue([saved()])
    vi.mocked(filtersApi.updateFilter).mockResolvedValue(saved())
    renderPanel()
    await waitFor(() => expect(screen.getByLabelText('Alta')).toBeChecked())

    await user.click(screen.getByLabelText('Baixa'))
    await user.click(screen.getByRole('button', { name: 'Salvar filtro' }))

    await waitFor(() => expect(filtersApi.updateFilter).toHaveBeenCalledTimes(1))
    expect(vi.mocked(filtersApi.updateFilter).mock.calls[0][0]).toBe(7)
    expect(filtersApi.createFilter).not.toHaveBeenCalled()
  })

  it('só habilita o botão Ouvir quando o filtro está salvo', async () => {
    const user = userEvent.setup()
    renderPanel()
    await screen.findByRole('option', { name: 'A Raposa e as Uvas' })
    expect(screen.getByRole('button', { name: 'Ouvir' })).toBeDisabled()

    vi.mocked(filtersApi.listFilters).mockResolvedValue([saved()])
    await user.click(screen.getByLabelText(/Português/))
    expect(screen.queryByRole('link', { name: 'Ouvir' })).not.toBeInTheDocument()
  })

  it('mostra erro quando não consegue salvar', async () => {
    const user = userEvent.setup()
    vi.mocked(filtersApi.createFilter).mockRejectedValue(new Error('falhou'))
    renderPanel()
    await screen.findByRole('option', { name: 'A Raposa e as Uvas' })
    await user.click(screen.getByLabelText(/Português/))
    await user.click(screen.getByLabelText('Phrasal verbs'))
    await user.click(screen.getByRole('button', { name: 'Salvar filtro' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível salvar o filtro')
  })

  it('Cenário C: mostra a densidade como final, a progressão crescente e a curva', async () => {
    const user = userEvent.setup()
    vi.mocked(filtersApi.createFilter).mockResolvedValue(saved())
    renderPanel()
    await screen.findByRole('option', { name: 'A Raposa e as Uvas' })

    await user.click(screen.getByLabelText(/Português/))
    expect(screen.getByText('Densidade')).toBeInTheDocument()
    expect(screen.queryByTestId('density-curve')).not.toBeInTheDocument()

    await user.click(screen.getByLabelText('Vocabulário avançado'))
    expect(screen.getByText('Densidade final')).toBeInTheDocument()
    const progressao = screen.getByRole('region', { name: 'Progressão da densidade' })
    expect(progressao).toHaveTextContent('Crescente')
    // o gráfico tem alternativa em texto: nome acessível e legenda com os valores
    expect(screen.getByRole('img', { name: /Curva de densidade de inglês/ })).toBeInTheDocument()
    expect(progressao).toHaveTextContent('O inglês começa em 7% das palavras escolhidas e sobe até 35% no final')

    await user.click(screen.getByRole('button', { name: 'Salvar filtro' }))
    await waitFor(() =>
      expect(filtersApi.createFilter).toHaveBeenCalledWith({
        story_id: 1,
        rules: {
          base_language: 'pt',
          segment_types: ['advanced_vocabulary'],
          density: 'medium',
          progression: 'increasing',
        },
      }),
    )
  })

  it('o gráfico muda quando a densidade final muda', async () => {
    const user = userEvent.setup()
    renderPanel()
    await user.click(await screen.findByLabelText(/Português/))
    await user.click(screen.getByLabelText('Vocabulário avançado'))
    const linha = () => screen.getByTestId('density-curve-line').getAttribute('points')

    const media = linha()
    await user.click(screen.getByLabelText('Alta'))
    expect(linha()).not.toBe(media)
    expect(screen.getByRole('img', { name: /sobe até 60% no final/ })).toBeInTheDocument()

    // a curva sobe do começo ao fim: o y (para baixo no SVG) diminui a cada ponto
    const ys = linha()!.split(' ').map((p) => Number(p.split(',')[1]))
    expect(ys.every((y, i) => i === 0 || y <= ys[i - 1])).toBe(true)
    expect(ys[ys.length - 1]).toBeLessThan(ys[0])
  })

  it('phrasal verbs e vocabulário avançado são cenários diferentes: escolher um desmarca o outro', async () => {
    const user = userEvent.setup()
    vi.mocked(filtersApi.createFilter).mockResolvedValue(saved())
    renderPanel()
    await screen.findByRole('option', { name: 'A Raposa e as Uvas' })

    await user.click(screen.getByLabelText(/Português/))
    await user.click(screen.getByLabelText('Phrasal verbs'))
    await user.click(screen.getByLabelText('Vocabulário avançado'))
    expect(screen.getByLabelText('Phrasal verbs')).not.toBeChecked()
    expect(screen.getByLabelText('Vocabulário avançado')).toBeChecked()

    await user.click(screen.getByLabelText('Phrasal verbs'))
    expect(screen.getByLabelText('Vocabulário avançado')).not.toBeChecked()
    expect(screen.queryByText('Densidade final')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Salvar filtro' }))

    // Cenário A: a progressão fixa é a padrão e não é enviada
    await waitFor(() =>
      expect(filtersApi.createFilter).toHaveBeenCalledWith({
        story_id: 1,
        rules: { base_language: 'pt', segment_types: ['phrasal_verbs'], density: 'medium' },
      }),
    )
  })

  it('o filtro do Cenário C salvo reaparece preenchido, com frases de exemplo do começo e do fim', async () => {
    vi.mocked(filtersApi.listFilters).mockResolvedValue([saved({ rules: SAVED_C })])
    renderPanel()

    await waitFor(() => expect(screen.getByLabelText('Vocabulário avançado')).toBeChecked())
    expect(screen.getByLabelText('Alta')).toBeChecked()
    expect(screen.getByText('Densidade final')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ouvir' })).toHaveAttribute('href', '/player/1?filter=7')

    expect(await screen.findByText('No começo:')).toBeInTheDocument()
    expect(storiesApi.getStoryPreview).toHaveBeenCalledWith(1, 7)
    expect(screen.getByText('famished')).toBeInTheDocument()
    expect(screen.getByText('No fim:')).toBeInTheDocument()
    expect(screen.getByText('disgruntled')).toBeInTheDocument()
  })

  it('não busca a prévia nos filtros de densidade fixa', async () => {
    vi.mocked(filtersApi.listFilters).mockResolvedValue([saved()])
    renderPanel()
    await waitFor(() => expect(screen.getByLabelText('Phrasal verbs')).toBeChecked())
    expect(storiesApi.getStoryPreview).not.toHaveBeenCalled()
    expect(screen.queryByTestId('density-curve')).not.toBeInTheDocument()
  })
})
