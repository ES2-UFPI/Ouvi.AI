import { AxiosError } from 'axios'
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import type { AudioGenerationStatus, GenerationState } from '../api'
import { POLL_MS, useGenerationStatus } from './useGenerationStatus'

vi.mock('../api')

const pedir = vi.mocked(api.requestStoryAudio)
const consultar = vi.mocked(api.getStoryAudioStatus)

function statusDe(state: GenerationState): AudioGenerationStatus {
  return { story_id: 1, filter_id: 7, state, total: 2, ready: state === 'ready' ? 2 : 0, failed: 0, segments: [] }
}

function erroHttp(status: number) {
  return new AxiosError('falhou', 'ERR_BAD_REQUEST', undefined, null, {
    status, data: {}, statusText: '', headers: {}, config: {} as never,
  })
}

const avancar = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms))

beforeEach(() => {
  vi.useFakeTimers()
  vi.resetAllMocks()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useGenerationStatus', () => {
  it('pede a geração e devolve o status; pronto, não consulta mais', async () => {
    pedir.mockResolvedValue(statusDe('ready'))
    const { result } = renderHook(() => useGenerationStatus(1, 7, true))

    await avancar(0)
    expect(pedir).toHaveBeenCalledWith(1, 7)
    expect(result.current.status?.state).toBe('ready')
    await avancar(POLL_MS * 3)
    expect(consultar).not.toHaveBeenCalled()
  })

  it('enquanto gera, consulta o status a cada intervalo até ficar pronto', async () => {
    pedir.mockResolvedValue(statusDe('generating'))
    consultar.mockResolvedValueOnce(statusDe('generating')).mockResolvedValue(statusDe('ready'))
    const { result } = renderHook(() => useGenerationStatus(1, 7, true))

    await avancar(0)
    expect(result.current.status?.state).toBe('generating')
    await avancar(POLL_MS)
    expect(consultar).toHaveBeenCalledTimes(1)
    await avancar(POLL_MS)
    expect(result.current.status?.state).toBe('ready')
    await avancar(POLL_MS * 3)
    expect(consultar).toHaveBeenCalledTimes(2) // parou ao ficar pronto
  })

  it('uma falha isolada de rede no polling não derruba o player', async () => {
    pedir.mockResolvedValue(statusDe('generating'))
    consultar.mockRejectedValueOnce(new Error('rede')).mockResolvedValue(statusDe('ready'))
    const { result } = renderHook(() => useGenerationStatus(1, 7, true))

    await avancar(POLL_MS * 3)

    expect(result.current.error).toBeNull()
    expect(result.current.status?.state).toBe('ready')
  })

  it('desiste depois de 5 falhas seguidas no polling', async () => {
    pedir.mockResolvedValue(statusDe('generating'))
    consultar.mockRejectedValue(new Error('rede'))
    const { result } = renderHook(() => useGenerationStatus(1, 7, true))

    await avancar(POLL_MS * 8)

    expect(result.current.error).toBe('Não foi possível gerar o áudio agora. Tente novamente em instantes.')
    expect(consultar).toHaveBeenCalledTimes(5)
  })

  it.each([
    [404, 'História ou filtro não encontrado.'],
    [422, 'Este filtro não pode ser usado com esta história.'],
    [500, 'Não foi possível gerar o áudio agora. Tente novamente em instantes.'],
  ])('erro %i ao pedir a geração mostra a mensagem certa', async (codigo, mensagem) => {
    pedir.mockRejectedValue(erroHttp(codigo))
    const { result } = renderHook(() => useGenerationStatus(1, 7, true))

    await avancar(0)

    expect(result.current.error).toBe(mensagem)
    expect(result.current.status).toBeNull()
  })

  it('desabilitado, ou sem filtro, não pede nada', async () => {
    renderHook(() => useGenerationStatus(1, 7, false))
    renderHook(() => useGenerationStatus(1, null, true))

    await avancar(POLL_MS * 2)

    expect(pedir).not.toHaveBeenCalled()
  })

  it('ao desmontar, para de consultar e ignora a resposta que chegar depois', async () => {
    pedir.mockResolvedValue(statusDe('generating'))
    consultar.mockResolvedValue(statusDe('generating'))
    const { unmount } = renderHook(() => useGenerationStatus(1, 7, true))
    await avancar(0)

    unmount()
    await avancar(POLL_MS * 4)

    expect(consultar).not.toHaveBeenCalled()
  })

  it('trocar de filtro recomeça: pede a geração do novo filtro', async () => {
    pedir.mockResolvedValue(statusDe('ready'))
    const { rerender } = renderHook(({ filtro }) => useGenerationStatus(1, filtro, true), { initialProps: { filtro: 7 } })
    await avancar(0)

    rerender({ filtro: 8 })
    await avancar(0)

    expect(pedir).toHaveBeenNthCalledWith(1, 1, 7)
    expect(pedir).toHaveBeenNthCalledWith(2, 1, 8)
  })
})
