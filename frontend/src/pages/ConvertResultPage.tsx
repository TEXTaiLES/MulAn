import { CheckCircle2, Download, Eye } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { ImageResource } from '../types'

export function ConvertResultPage() {
  const { imageId = '' } = useParams(); const [image, setImage] = useState<ImageResource | null>(() => { const saved = sessionStorage.getItem(`mulan:image:${imageId}`); return saved ? JSON.parse(saved) : null }); const [error, setError] = useState('')
  useEffect(() => { if (!image) api.image(imageId).then(setImage).catch(reason => setError(reason.message)) }, [image, imageId])
  if (error) return <div className="page narrow"><p className="error">{error}</p></div>
  if (!image) return <div className="page narrow"><p>Loading result…</p></div>
  return <div className="page narrow result-card"><CheckCircle2 className="success-icon" /><span className="eyebrow">Conversion complete</span><h1>Your TIFF is ready</h1><h2>{image.filename}</h2><div className="metadata-grid"><span><small>Dimensions</small>{image.width} × {image.height}</span><span><small>Channels</small>{image.channel_count}</span><span><small>Names</small>{image.channel_names?.filter(Boolean).join(', ') || 'Not provided'}</span></div><a className="primary large button-link" href={`/api/v1/images/${image.image_id}/file`} download><Download />Download TIF</a><Link className="secondary button-link" to={`/viewer?image_id=${image.image_id}`}><Eye />Open in Viewer</Link></div>
}

