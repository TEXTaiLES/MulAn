import { UploadCloud } from 'lucide-react'
import { useRef, useState } from 'react'

export function UploadDropzone({ accept, multiple = false, onFiles, title, description }: { accept: string; multiple?: boolean; onFiles: (files: File[]) => void; title: string; description: string }) {
  const input = useRef<HTMLInputElement>(null); const [drag, setDrag] = useState(false)
  const choose = (list: FileList | null) => { if (list?.length) onFiles(Array.from(list)) }
  return <div className={`dropzone ${drag ? 'dragging' : ''}`} onDragEnter={event => { event.preventDefault(); setDrag(true) }} onDragOver={event => event.preventDefault()} onDragLeave={() => setDrag(false)} onDrop={event => { event.preventDefault(); setDrag(false); choose(event.dataTransfer.files) }}>
    <UploadCloud size={48} />
    <h2>{title}</h2><p>{description}</p>
    <button className="primary" onClick={() => input.current?.click()}>Select {multiple ? 'files' : 'file'}</button>
    <input ref={input} className="visually-hidden" aria-label={title} type="file" accept={accept} multiple={multiple} onChange={event => choose(event.target.files)} />
  </div>
}

