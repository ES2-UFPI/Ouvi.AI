import { useCallback, useEffect, useRef, useState } from 'react'

export const SPEEDS = [0.75, 1, 1.25, 1.5, 2]

export function useAudioPlayer() {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [speed, setSpeedState] = useState(1)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return

    // Mudar a velocidade não pode mudar o tom da voz (a maioria dos navegadores já faz isso por padrão)
    audio.preservesPitch = true

    const onTimeUpdate = () => setCurrentTime(audio.currentTime)
    const onLoadedMetadata = () => setDuration(audio.duration)
    const onEnded = () => setIsPlaying(false)
    const onPlay = () => setIsPlaying(true)
    const onPause = () => setIsPlaying(false)
    // loadstart e waiting: está buscando dados; canplay e playing: já tem o que tocar
    const onBusy = () => setIsLoading(true)
    const onReady = () => setIsLoading(false)
    const onError = () => {
      setIsLoading(false)
      setIsPlaying(false)
      setError('Não foi possível carregar o áudio.')
    }

    const listeners: [string, () => void][] = [
      ['timeupdate', onTimeUpdate],
      ['loadedmetadata', onLoadedMetadata],
      ['ended', onEnded],
      ['play', onPlay],
      ['pause', onPause],
      ['loadstart', onBusy],
      ['waiting', onBusy],
      ['canplay', onReady],
      ['playing', onReady],
      ['error', onError],
    ]
    listeners.forEach(([name, fn]) => audio.addEventListener(name, fn))
    return () => listeners.forEach(([name, fn]) => audio.removeEventListener(name, fn))
  }, [])

  const togglePlay = useCallback(() => {
    const audio = audioRef.current
    if (!audio) return
    if (audio.paused) {
      setIsPlaying(true)
      audio.play().catch(() => {
        // Play recusado (ex.: o navegador bloqueou ou o arquivo não carregou)
        setIsPlaying(false)
        setError('Não foi possível reproduzir o áudio.')
      })
    } else {
      audio.pause()
      setIsPlaying(false)
    }
  }, [])

  const seek = useCallback((deltaSeconds: number) => {
    const audio = audioRef.current
    if (!audio) return
    const next = Math.min(Math.max(audio.currentTime + deltaSeconds, 0), audio.duration || 0)
    audio.currentTime = next
  }, [])

  const seekTo = useCallback((time: number) => {
    const audio = audioRef.current
    if (!audio) return
    audio.currentTime = time
  }, [])

  const setSpeed = useCallback((value: number) => {
    if (audioRef.current) audioRef.current.playbackRate = value
    setSpeedState(value)
  }, [])

  return {
    audioRef,
    isPlaying,
    isLoading,
    error,
    currentTime,
    duration,
    speed,
    togglePlay,
    seek,
    seekTo,
    setSpeed,
  }
}
