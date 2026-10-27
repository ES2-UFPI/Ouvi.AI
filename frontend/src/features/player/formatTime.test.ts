import { describe, it, expect } from 'vitest'
import { formatTime } from './formatTime'

describe('formatTime', () => {
  it('formata segundos menores que um minuto', () => {
    expect(formatTime(45)).toBe('0:45')
  })

  it('formata minutos e segundos', () => {
    expect(formatTime(125)).toBe('2:05')
  })

  it('retorna 0:00 para valores inválidos', () => {
    expect(formatTime(NaN)).toBe('0:00')
    expect(formatTime(-10)).toBe('0:00')
  })

  it('arredonda segundos fracionados para baixo', () => {
    expect(formatTime(59.9)).toBe('0:59')
  })
})