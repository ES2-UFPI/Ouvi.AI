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

  it('cicla a velocidade ao clicar no botão de velocidade', () => {
    render(<AudioPlayer src="teste.mp3" />)
    fireEvent.click(screen.getByText('1x'))
    expect(screen.getByText('1.25x')).toBeInTheDocument()
  })

  it('não quebra ao clicar em avançar/voltar 15s sem áudio carregado', () => {
    render(<AudioPlayer src="teste.mp3" />)
    expect(() => {
      fireEvent.click(screen.getByLabelText('Avançar 15 segundos'))
      fireEvent.click(screen.getByLabelText('Voltar 15 segundos'))
    }).not.toThrow()
  })
})