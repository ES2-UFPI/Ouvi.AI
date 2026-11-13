import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SAVE_INTERVAL_MS, useProgressSaver, type ListenPosition } from './useProgressSaver'
import * as api from './api'

vi.mock('./api')

const saveProgress = vi.mocked(api.saveProgress)
const saveOnExit = vi.mocked(api.saveProgressOnExit)

// Posição que o teste move à vontade: o hook a lê na hora de cada salvamento
let position: ListenPosition | null

function setup(initial: { playing: boolean; enabled?: boolean }) {
  return renderHook(
    (props: { playing: boolean; enabled: boolean }) =>
      useProgressSaver({ storyId: 1, filterId: 7, getPosition: () => position, ...props }),
    { initialProps: { enabled: true, ...initial } },
  )
}

const avancar = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms))

beforeEach(() => {
  vi.useFakeTimers()
  position = { segmentPosition: 2, offsetMs: 1000 }
  saveProgress.mockReset().mockResolvedValue({} as never)
  saveOnExit.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useProgressSaver', () => {
  it('envia a posição a cada 5 segundos enquanto o áudio toca', async () => {
    setup({ playing: true })

    await avancar(SAVE_INTERVAL_MS)
    expect(saveProgress).toHaveBeenCalledTimes(1)
    expect(saveProgress).toHaveBeenLastCalledWith(1, {
      segment_position: 2,
      offset_ms: 1000,
      filter_id: 7,
      completed: false,
    })

    position = { segmentPosition: 2, offsetMs: 6000 }
    await avancar(SAVE_INTERVAL_MS)
    expect(saveProgress).toHaveBeenCalledTimes(2)
    expect(saveProgress).toHaveBeenLastCalledWith(1, expect.objectContaining({ offset_ms: 6000 }))
  })

  it('não envia nada com a página parada ou pausada', async () => {
    setup({ playing: false })
    await avancar(SAVE_INTERVAL_MS * 3)
    expect(saveProgress).not.toHaveBeenCalled()
  })

  it('não repete a mesma posição', async () => {
    setup({ playing: true })
    await avancar(SAVE_INTERVAL_MS * 3) // a posição não mudou em nenhum dos 3 ciclos
    expect(saveProgress).toHaveBeenCalledTimes(1)
  })

  it('ao pausar, envia a posição na hora', async () => {
    const { rerender } = setup({ playing: true })
    position = { segmentPosition: 3, offsetMs: 2500 }

    rerender({ enabled: true, playing: false })
    await avancar(0)

    expect(saveProgress).toHaveBeenCalledTimes(1)
    expect(saveProgress).toHaveBeenLastCalledWith(1, expect.objectContaining({ segment_position: 3, offset_ms: 2500 }))
  })

  it('ao esconder a aba ou fechar a página, envia a posição', () => {
    setup({ playing: true })

    act(() => {
      window.dispatchEvent(new Event('pagehide'))
    })
    expect(saveOnExit).toHaveBeenCalledTimes(1)
    expect(saveOnExit).toHaveBeenLastCalledWith(1, expect.objectContaining({ segment_position: 2, offset_ms: 1000 }))

    position = { segmentPosition: 2, offsetMs: 4000 }
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })
    expect(saveOnExit).toHaveBeenCalledTimes(2)
    expect(saveOnExit).toHaveBeenLastCalledWith(1, expect.objectContaining({ offset_ms: 4000 }))
  })

  it('ao sair da tela por um link da aplicação (sem fechar a página), envia a posição', () => {
    const { unmount } = setup({ playing: true })
    position = { segmentPosition: 4, offsetMs: 3200 }

    unmount()

    expect(saveOnExit).toHaveBeenCalledTimes(1)
    expect(saveOnExit).toHaveBeenLastCalledWith(1, expect.objectContaining({ segment_position: 4, offset_ms: 3200 }))
  })

  it('ao sair da tela sem nada novo para guardar ou antes da escolha de retomar, não envia', async () => {
    const pronto = setup({ playing: true })
    await avancar(SAVE_INTERVAL_MS) // salva a posição atual
    saveOnExit.mockClear()
    pronto.unmount() // a posição não mudou desde o último salvamento
    expect(saveOnExit).not.toHaveBeenCalled()

    const aguardando = setup({ playing: false, enabled: false })
    aguardando.unmount()
    expect(saveOnExit).not.toHaveBeenCalled()
  })

  it('ao voltar para a aba não envia nada', () => {
    setup({ playing: true })
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })
    expect(saveOnExit).not.toHaveBeenCalled()
  })

  it('uma falha de rede é ignorada e a posição vai no ciclo seguinte', async () => {
    saveProgress.mockRejectedValueOnce(new Error('sem rede'))
    setup({ playing: true })

    await avancar(SAVE_INTERVAL_MS) // falha: nada estoura e nada é mostrado
    expect(saveProgress).toHaveBeenCalledTimes(1)

    await avancar(SAVE_INTERVAL_MS) // a mesma posição ainda não foi salva: tenta de novo
    expect(saveProgress).toHaveBeenCalledTimes(2)
    await avancar(SAVE_INTERVAL_MS) // agora salvou: não repete
    expect(saveProgress).toHaveBeenCalledTimes(2)
  })

  it('nunca há duas requisições de progresso ao mesmo tempo', async () => {
    let finish: () => void = () => undefined
    saveProgress.mockReset().mockImplementation(() => new Promise((resolve) => (finish = () => resolve({} as never))))
    const { rerender } = setup({ playing: true })

    await avancar(SAVE_INTERVAL_MS)
    expect(saveProgress).toHaveBeenCalledTimes(1) // a primeira ainda está a caminho

    position = { segmentPosition: 2, offsetMs: 9000 }
    rerender({ enabled: true, playing: false }) // pausar pede outro salvamento
    await avancar(0)
    expect(saveProgress).toHaveBeenCalledTimes(1) // espera a vez

    await act(async () => finish())
    await avancar(0)
    expect(saveProgress).toHaveBeenCalledTimes(2) // depois que a primeira acabou
    expect(saveProgress).toHaveBeenLastCalledWith(1, expect.objectContaining({ offset_ms: 9000 }))
  })

  it('ao terminar a história, marca como concluída', async () => {
    const { result } = setup({ playing: false })

    act(() => result.current.markCompleted({ segmentPosition: 11, offsetMs: 0 }))
    await avancar(0)

    expect(saveProgress).toHaveBeenCalledWith(1, {
      segment_position: 11,
      offset_ms: 0,
      filter_id: 7,
      completed: true,
    })
  })

  it('não salva enquanto o usuário não escolheu continuar ou recomeçar', async () => {
    const { result } = setup({ playing: true, enabled: false })

    await avancar(SAVE_INTERVAL_MS * 2)
    act(() => {
      window.dispatchEvent(new Event('pagehide'))
      result.current.markCompleted({ segmentPosition: 1, offsetMs: 0 })
    })

    expect(saveProgress).not.toHaveBeenCalled()
    expect(saveOnExit).not.toHaveBeenCalled()
  })

  it('sem posição para salvar (nada tocando ainda), não envia', async () => {
    position = null
    setup({ playing: true })
    await avancar(SAVE_INTERVAL_MS * 2)
    expect(saveProgress).not.toHaveBeenCalled()
  })
})
