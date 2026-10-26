import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { AudioPlayer } from './AudioPlayer'

export function PlayerPage() {
  const { materialId } = useParams<{ materialId: string }>()
  const navigate = useNavigate()

  const apiUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
  const streamUrl = `${apiUrl}/materials/${materialId}/stream`

  return (
    <div className="min-h-screen bg-bg-deep px-6 py-10">
      <div className="max-w-md mx-auto">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1.5 text-text-muted hover:text-text-primary transition-colors text-sm mb-6"
        >
          <ArrowLeft size={16} />
          Voltar
        </button>

        <AudioPlayer src={streamUrl} title="Sua história" />
      </div>
    </div>
  )
}