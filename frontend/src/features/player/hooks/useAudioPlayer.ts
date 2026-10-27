import { useCallback, useEffect, useRef, useState } from 'react'

const SPEEDS = [0.75, 1, 1.25, 1.5, 2]

export function useAudioPlayer() {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [speedIndex, setSpeedIndex] = useState(1) // índice 1 = 1x

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return

    const onTimeUpdate = () => setCurrentTime(audio.currentTime)
    const onLoadedMetadata = () => setDuration(audio.duration)
    const onEnded = () => setIsPlaying(false)

    audio.addEventListener('timeupdate', onTimeUpdate)
    audio.addEventListener('loadedmetadata', onLoadedMetadata)
    audio.addEventListener('ended', onEnded)

    return () => {
      audio.removeEventListener('timeupdate', onTimeUpdate)
      audio.removeEventListener('loadedmetadata', onLoadedMetadata)
      audio.removeEventListener('ended', onEnded)
    }
  }, [])

  const togglePlay = useCallback(() => {
    const audio = audioRef.current
    if (!audio) return
    if (audio.paused) {
      audio.play()
      setIsPlaying(true)
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

  const cycleSpeed = useCallback(() => {
    setSpeedIndex((prev) => {
      const next = (prev + 1) % SPEEDS.length
      if (audioRef.current) audioRef.current.playbackRate = SPEEDS[next]
      return next
    })
  }, [])

  return {
    audioRef,
    isPlaying,
    currentTime,
    duration,
    speed: SPEEDS[speedIndex],
    togglePlay,
    seek,
    seekTo,
    cycleSpeed,
  }
}