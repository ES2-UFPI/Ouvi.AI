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
  { id: 1, title: 'A Raposa e as Uvas', description: null },
  { id: 2, title: 'A Lebre e a Tartaruga', description: null },
]

const saved = (overrides = {}) => ({
  id: 7,
  story_id: 1,
  rules: { base_language: 'pt' as const, segment_types: ['phrasal_verbs' as const], density: 'high' as const },
  created_at: '',
  updated_at: '',
  ...overrides,
})

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
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
})

// Resposta de GET /filters/options (tabela de combinações do backend)
const OPTIONS = {
  scenarios: [
    { base_language: 'pt' as const, segment_types: ['phrasal_verbs' as const], word_levels: [], description: 'Cenário A' },
    {
      base_language: 'en' as const,
      segment_types: ['difficult_words' as const],
      word_levels: ['intermediate' as const, 'advanced' as const],
      description: 'Cenário B',
    },
  ],
  densities: ['low' as const, 'medium' as const, 'high' as const],
  word_levels: ['intermediate' as const, 'advanced' as const],
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
  it('lista as histórias e as opções de idioma base e densidade', async () => {
    renderPanel()
    expect(await screen.findByRole('option', { name: 'A Raposa e as Uvas' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'A Lebre e a Tartaruga' })).toBeInTheDocument()
    expect(screen.getByLabelText(/Português/)).toBeInTheDocument()
    expect(screen.getByLabelText(/English/)).toBeInTheDocument()
    expect(screen.getByText('Escolha o idioma base para ver os tipos de trecho.')).toBeInTheDocument()
    for (const label of ['Baixa', 'Média', 'Alta']) expect(screen.getByLabelText(label)).toBeInTheDocument()
  })

  it('português mostra só phrasal verbs, sem o campo de nível', async () => {
    const user = userEvent.setup()
    renderPanel()
    await waitFor(() => expect(filtersApi.getFilterOptions).toHaveBeenCalled())
    await user.click(await screen.findByLabelText(/Português/))
    expect(screen.getByLabelText('Phrasal verbs')).toBeInTheDocument()
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
})
