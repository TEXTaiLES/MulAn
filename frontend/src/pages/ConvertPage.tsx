import { closestCenter, DndContext, type DragEndEvent, KeyboardSensor, PointerSensor, useSensor, useSensors } from '@dnd-kit/core'
import { arrayMove, SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { ArrowDown, ArrowUp, GripVertical, Plus, Trash2 } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiFailure } from '../api/client'
import { UploadDropzone } from '../components/UploadDropzone'

type Band = { id: string; file: File; name: string }

function SortableBand({ band, index, count, error, onMove, onDelete, onName }: { band: Band; index: number; count: number; error?: string; onMove: (from: number, to: number) => void; onDelete: () => void; onName: (name: string) => void }) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: band.id })
  return <div ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition }} className="band-row">
    <button className="drag-handle" aria-label={`Drag Channel ${index + 1}`} {...attributes} {...listeners}><GripVertical /></button>
    <span className="channel-badge">Channel {index + 1}</span><div className="band-info"><strong>{band.file.name}</strong><small>{Math.ceil(band.file.size / 1024)} KB</small>{error && <small className="band-file-error" role="alert">{error}</small>}</div>
    <input aria-label={`Channel ${index + 1} name`} placeholder="Optional name, e.g. 550nm" value={band.name} onChange={event => onName(event.target.value)} />
    <button title="Move up" aria-label={`Move Channel ${index + 1} up`} disabled={index === 0} onClick={() => onMove(index, index - 1)}><ArrowUp /></button>
    <button title="Move down" aria-label={`Move Channel ${index + 1} down`} disabled={index === count - 1} onClick={() => onMove(index, index + 1)}><ArrowDown /></button>
    <button className="danger-icon" title="Remove" aria-label={`Remove ${band.file.name}`} onClick={onDelete}><Trash2 /></button>
  </div>
}

export function ConvertPage() {
  const [bands, setBands] = useState<Band[]>([]); const [error, setError] = useState(''); const [bandErrors, setBandErrors] = useState<Record<string, string>>({}); const [busy, setBusy] = useState(false); const addInput = useRef<HTMLInputElement>(null); const navigate = useNavigate()
  const sensors = useSensors(useSensor(PointerSensor), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }))
  const add = (files: File[]) => {
    const invalid = files.find(file => !/\.bmp$/i.test(file.name))
    if (invalid) { setError(`${invalid.name} is not a BMP file.`); return }
    setError(''); setBandErrors({}); setBands(current => [...current, ...files.map(file => ({ id: `${file.name}-${file.size}-${file.lastModified}-${crypto.randomUUID()}`, file, name: '' }))])
  }
  const ids = useMemo(() => bands.map(item => item.id), [bands])
  const dragEnd = ({ active, over }: DragEndEvent) => { if (over && active.id !== over.id) setBands(items => arrayMove(items, items.findIndex(item => item.id === active.id), items.findIndex(item => item.id === over.id))) }
  const move = (from: number, to: number) => setBands(items => arrayMove(items, from, to))
  const convert = async () => {
    setBusy(true); setError(''); setBandErrors({})
    try {
      const result = await api.convert(bands.map(item => item.file), bands.map(item => item.name || null))
      sessionStorage.setItem(`mulan:image:${result.image_id}`, JSON.stringify(result)); navigate(`/convert/result/${result.image_id}`)
    } catch (reason) {
      const message = reason instanceof ApiFailure ? reason.message : 'Conversion failed.'
      setError(message)
      if (reason instanceof ApiFailure && typeof reason.details.file === 'string') setBandErrors(Object.fromEntries(bands.filter(item => item.file.name === reason.details.file).map(item => [item.id, message])))
    } finally { setBusy(false) }
  }
  if (!bands.length) return <div className="page tool-page"><div className="page-heading"><span className="eyebrow">Converter</span><h1>BMP bands to multispectral TIFF</h1><p>Order matters: each grayscale BMP becomes one TIFF channel.</p></div><UploadDropzone accept=".bmp,image/bmp" multiple title="Drop grayscale BMP bands here" description="Every file must have the same dimensions and sample datatype." onFiles={add} />{error && <p className="error" role="alert">{error}</p>}</div>
  return <div className="page tool-page"><div className="page-heading compact"><span className="eyebrow">Converter</span><h1>Arrange your channels</h1><p>Drag rows or use the arrow buttons. The first row becomes TIFF Band 1.</p></div>
    {error && <p className="error" role="alert">{error}</p>}
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={dragEnd}><SortableContext items={ids} strategy={verticalListSortingStrategy}><div className="band-list">{bands.map((band, index) => <SortableBand key={band.id} band={band} index={index} count={bands.length} error={bandErrors[band.id]} onMove={move} onDelete={() => setBands(items => items.filter(item => item.id !== band.id))} onName={name => setBands(items => items.map(item => item.id === band.id ? { ...item, name } : item))} />)}</div></SortableContext></DndContext>
    <div className="action-row"><button className="secondary" onClick={() => addInput.current?.click()}><Plus />Add more bands</button><input ref={addInput} className="visually-hidden" type="file" accept=".bmp,image/bmp" multiple onChange={event => add(Array.from(event.target.files || []))} /><button className="primary large" disabled={busy || !bands.length} onClick={convert}>{busy ? 'Converting…' : 'Convert to TIF'}</button></div>
  </div>
}
