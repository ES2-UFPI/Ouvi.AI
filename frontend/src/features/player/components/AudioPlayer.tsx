import { Play, Pause } from 'lucide-react'
import { useAudioPlayer } from '../hooks/useAudioPlayer'
import { formatTime } from '../formatTime'

interface AudioPlayerProps {
  src: string
  title?: string
}

export function AudioPlayer({ src, title }: AudioPlayerProps) {
  const { audioRef, isPlaying, currentTime, duration, speed, togglePlay, seek, seekTo, cycleSpeed } =
    useAudioPlayer()

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0

  function handleScrub(e: React.ChangeEvent<HTMLInputElement>) {
    const percent = Number(e.target.value)
    seekTo((percent / 100) * duration)
  }

  return (
    <div className="rounded-xl bg-bg-surface border border-border-subtle p-5">
      <audio ref={audioRef} src={src} preload="metadata" />

      {title && <p className="font-display text-text-primary mb-4">{title}</p>}

      <input
        type="range"
        min={0}
        max={100}
        step={0.1}
        value={progress}
        onChange={handleScrub}
        className="pt-en-slider w-full"
        style={{
          background: `linear-gradient(to right, var(--color-accent-en) 0%, var(--color-accent-en) ${progress}%, var(--color-border-subtle) ${progress}%, var(--color-border-subtle) 100%)`,
        }}
        aria-label="Progresso da faixa"
      />

      <div className="flex justify-between text-xs text-text-muted mt-1.5 mb-5">
        <span>{formatTime(currentTime)}</span>
        <span>{formatTime(duration)}</span>
      </div>

      <div className="flex items-center justify-center gap-6">
        <button
          type="button"
          onClick={() => seek(-15)}
          className="text-text-muted hover:text-text-primary transition-colors text-sm font-medium"
          aria-label="Voltar 15 segundos"
        >
          −15s
        </button>

        <button
          type="button"
          onClick={togglePlay}
          className="w-12 h-12 rounded-full flex items-center justify-center text-bg-deep"
          style={{ backgroundColor: 'var(--color-accent-en)' }}
          aria-label={isPlaying ? 'Pausar' : 'Reproduzir'}
        >
          {isPlaying ? (
            <Pause size={20} fill="currentColor" />
          ) : (
            <Play size={20} fill="currentColor" className="ml-0.5" />
          )}
        </button>

        <button
          type="button"
          onClick={() => seek(15)}
          className="text-text-muted hover:text-text-primary transition-colors text-sm font-medium"
          aria-label="Avançar 15 segundos"
        >
          +15s
        </button>
      </div>

      <div className="flex justify-center mt-4">
        <button
          type="button"
          onClick={cycleSpeed}
          className="text-xs px-2.5 py-1 rounded-full border border-border-subtle text-text-muted hover:text-text-primary hover:border-text-primary transition-colors"
        >
          {speed}x
        </button>
      </div>
    </div>
  )
}