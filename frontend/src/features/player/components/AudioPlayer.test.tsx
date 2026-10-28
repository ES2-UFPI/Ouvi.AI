import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AudioPlayer } from './AudioPlayer'

describe('AudioPlayer', () => {
  it('renderiza no estado pausado inicialmente', () => {
    render(<AudioPlayer src="teste.mp3" title="Minha história" />)
    expect(screen.getByText('Minha história')).toBeInTheDocument()
    expect(screen.getByLabelText('Reproduzir')).toBeInTheDocument()
  })

  it('alterna para pausar ao clicar em play', () => {
    render(<AudioPlayer src="teste.mp3" />)
    fireEvent.click(screen.getByLabelText('Reproduzir'))
    expect(screen.getByLabelText('Pausar')).toBeInTheDocument()
  })

  it('oferece as cinco velocidades e marca a escolhida', () => {
    render(<AudioPlayer src="teste.mp3" />)
    for (const label of ['0,75x', '1x', '1,25x', '1,5x', '2x']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
    }
    expect(screen.getByRole('button', { name: '1x' })).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(screen.getByRole('button', { name: '1,25x' }))
    expect(screen.getByRole('button', { name: '1,25x' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '1x' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('aplica a velocidade ao áudio sem mudar o tom', () => {
    const { container } = render(<AudioPlayer src="teste.mp3" />)
    fireEvent.click(screen.getByRole('button', { name: '1,5x' }))
    const audio = container.querySelector('audio')!
    expect(audio.playbackRate).toBe(1.5)
    expect(audio.preservesPitch).toBe(true)
  })

  it('não quebra ao clicar em avançar/voltar 15s sem áudio carregado', () => {
    render(<AudioPlayer src="teste.mp3" />)
    expect(() => {
      fireEvent.click(screen.getByLabelText('Avançar 15 segundos'))
      fireEvent.click(screen.getByLabelText('Voltar 15 segundos'))
    }).not.toThrow()
  })

  it('indica que está carregando e depois que o áudio pode tocar', () => {
    const { container } = render(<AudioPlayer src="teste.mp3" />)
    expect(screen.getByRole('status')).toHaveTextContent('Carregando áudio')

    fireEvent(container.querySelector('audio')!, new Event('canplay'))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('mostra um erro quando o áudio não carrega', () => {
    const { container } = render(<AudioPlayer src="teste.mp3" />)
    fireEvent(container.querySelector('audio')!, new Event('error'))
    expect(screen.getByRole('alert')).toHaveTextContent('Não foi possível carregar o áudio')
  })

  it('a barra de progresso e os botões têm rótulo para leitores de tela', () => {
    render(<AudioPlayer src="teste.mp3" />)
    expect(screen.getByLabelText('Progresso da faixa')).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Velocidade de reprodução' })).toBeInTheDocument()
  })
})
