import { Headphones, Play, Pause } from 'lucide-react'
import { SPEEDS, useAudioPlayer } from '../hooks/useAudioPlayer'
import { formatTime } from '../formatTime'

interface AudioPlayerProps {
  src: string
  title?: string
  // Etiquetas com o resumo do filtro escolhido (opcional)
  chips?: string[]
}

const formatSpeed = (value: number) => `${String(value).replace('.', ',')}x`

export function AudioPlayer({ src, title, chips = [] }: AudioPlayerProps) {
  const {
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
  } = useAudioPlayer()

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0

  function handleScrub(e: React.ChangeEvent<HTMLInputElement>) {
    const percent = Number(e.target.value)
    seekTo((percent / 100) * duration)
  }

  return (
    <div className="rounded-2xl bg-bg-surface border border-border-subtle p-7 shadow-2xl shadow-black/40">
      <audio ref={audioRef} src={src} preload="metadata" />

      <div className="flex items-center gap-3 mb-1">
        <span
          className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--color-accent-en) 15%, transparent)',
            color: 'var(--color-accent-en)',
          }}
        >
          <Headphones size={20} />
        </span>
        {title && <h2 className="font-display text-2xl text-text-primary leading-tight">{title}</h2>}
      </div>

      {chips.length > 0 ? (
        <ul className="flex flex-wrap gap-2 mt-4 mb-7" aria-label="Filtro escolhido">
          {chips.map((chip) => (
            <li
              key={chip}
              className="text-xs rounded-full border border-border-subtle px-2.5 py-1 text-text-muted"
            >
              {chip}
            </li>
          ))}
        </ul>
      ) : (
        <div className="mb-7" />
      )}

      <input
        type="range"
        min={0}
        max={100}
        step={0.1}
        value={progress}
        onChange={handleScrub}
        disabled={duration === 0}
        className="pt-en-slider w-full"
        style={{
          background: `linear-gradient(to right, var(--color-accent-en) 0%, var(--color-accent-en) ${progress}%, var(--color-border-subtle) ${progress}%, var(--color-border-subtle) 100%)`,
        }}
        aria-label="Progresso da faixa"
        aria-valuetext={`${formatTime(currentTime)} de ${formatTime(duration)}`}
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
          className="w-16 h-16 rounded-full flex items-center justify-center text-bg-deep transition hover:brightness-110 shadow-lg"
          style={{
            backgroundColor: 'var(--color-accent-en)',
            boxShadow: '0 8px 24px color-mix(in srgb, var(--color-accent-en) 35%, transparent)',
          }}
          aria-label={isPlaying ? 'Pausar' : 'Reproduzir'}
        >
          {isPlaying ? (
            <Pause size={26} fill="currentColor" />
          ) : (
            <Play size={26} fill="currentColor" className="ml-1" />
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

      <p className="text-xs uppercase tracking-wider text-text-muted text-center mt-7 mb-2.5">Velocidade</p>
      <div role="group" aria-label="Velocidade de reprodução" className="grid grid-cols-5 gap-2">
        {SPEEDS.map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => setSpeed(value)}
            aria-pressed={speed === value}
            className="text-xs py-2 rounded-xl border transition-colors hover:border-text-muted"
            style={{
              borderColor: speed === value ? 'var(--color-accent-pt)' : 'var(--color-border-subtle)',
              backgroundColor:
                speed === value ? 'color-mix(in srgb, var(--color-accent-pt) 14%, transparent)' : 'transparent',
              color: speed === value ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
            }}
          >
            {formatSpeed(value)}
          </button>
        ))}
      </div>

      <div className="min-h-5 mt-3 text-center text-xs">
        {error ? (
          <p role="alert" style={{ color: 'var(--color-accent-pt)' }}>
            {error}
          </p>
        ) : (
          isLoading && (
            <p role="status" className="text-text-muted">
              Carregando áudio...
            </p>
          )
        )}
      </div>
    </div>
  )
}
