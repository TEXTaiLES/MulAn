import { closestCenter, DndContext, type DragEndEvent, KeyboardSensor, PointerSensor, useSensor, useSensors } from '@dnd-kit/core'
import { arrayMove, SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { ArrowDown, ArrowUp, GripVertical, Plus, Trash2 } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiFailure } from '../api/client'
import { UploadDropzone } from '../components/UploadDropzone'

type Band = { id: string; file: File; channelCount: 1 | 3; names: string[] }

function readBlob(blob: Blob): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as ArrayBuffer)
    reader.onerror = () => reject(reader.error)
    reader.readAsArrayBuffer(blob)
  })
}

async function bmpChannelCount(file: File): Promise<1 | 3> {
  try {
    const buffer = await readBlob(file.slice(0, 54))
    const view = new DataView(buffer)
    if (view.byteLength < 30 || view.getUint8(0) !== 0x42 || view.getUint8(1) !== 0x4d) return 1
    const dibSize = view.getUint32(14, true)
    const bitsPerPixel = dibSize === 12 && view.byteLength >= 26 ? view.getUint16(24, true) : view.getUint16(28, true)
    return bitsPerPixel > 8 ? 3 : 1
  } catch {
    return 1 // The backend remains authoritative for malformed or uncommon BMP layouts.
  }
}

function SortableBand({ band, index, count, outputStart, error, onMove, onDelete, onName }: { band: Band; index: number; count: number; outputStart: number; error?: string; onMove: (from: number, to: number) => void; onDelete: () => void; onName: (index: number, name: string) => void }) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: band.id })
  return <div ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition }} className="band-row">
    <button className="drag-handle" aria-label={`Drag Channel ${index + 1}`} {...attributes} {...listeners}><GripVertical /></button>
    <span className="channel-badge">{band.channelCount === 1 ? `Channel ${outputStart + 1}` : `Channels ${outputStart + 1}–${outputStart + 3}`}</span><div className="band-info"><strong>{band.file.name}</strong><small>{band.channelCount === 3 ? 'RGB · 3 channels' : 'Grayscale · 1 channel'} · {Math.ceil(band.file.size / 1024)} KB</small>{error && <small className="band-file-error" role="alert">{error}</small>}</div>
    <div className="band-names">{band.names.map((name, componentIndex) => <input key={componentIndex} aria-label={`Channel ${outputStart + componentIndex + 1} name`} placeholder={band.channelCount === 3 ? `${'RGB'[componentIndex]} name (optional)` : 'Optional name, e.g. 550nm'} value={name} onChange={event => onName(componentIndex, event.target.value)} />)}</div>
    <button title="Move up" aria-label={`Move Channel ${index + 1} up`} disabled={index === 0} onClick={() => onMove(index, index - 1)}><ArrowUp /></button>
    <button title="Move down" aria-label={`Move Channel ${index + 1} down`} disabled={index === count - 1} onClick={() => onMove(index, index + 1)}><ArrowDown /></button>
    <button className="danger-icon" title="Remove" aria-label={`Remove ${band.file.name}`} onClick={onDelete}><Trash2 /></button>
  </div>
}

export function ConvertPage() {
  const [bands, setBands] = useState<Band[]>([]); const [error, setError] = useState(''); const [bandErrors, setBandErrors] = useState<Record<string, string>>({}); const [busy, setBusy] = useState(false); const addInput = useRef<HTMLInputElement>(null); const navigate = useNavigate()
  const sensors = useSensors(useSensor(PointerSensor), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }))
  const add = async (files: File[]) => {
    const invalid = files.find(file => !/\.bmp$/i.test(file.name))
    if (invalid) { setError(`${invalid.name} is not a BMP file.`); return }
    const additions = await Promise.all(files.map(async file => {
      const channelCount = await bmpChannelCount(file)
      return { id: `${file.name}-${file.size}-${file.lastModified}-${crypto.randomUUID()}`, file, channelCount, names: Array<string>(channelCount).fill('') }
    }))
    setError(''); setBandErrors({}); setBands(current => [...current, ...additions])
  }
  const ids = useMemo(() => bands.map(item => item.id), [bands])
  const outputCount = useMemo(() => bands.reduce((total, item) => total + item.channelCount, 0), [bands])
  const dragEnd = ({ active, over }: DragEndEvent) => { if (over && active.id !== over.id) setBands(items => arrayMove(items, items.findIndex(item => item.id === active.id), items.findIndex(item => item.id === over.id))) }
  const move = (from: number, to: number) => setBands(items => arrayMove(items, from, to))
  const convert = async () => {
    setBusy(true); setError(''); setBandErrors({})
    try {
      const result = await api.convert(bands.map(item => item.file), bands.flatMap(item => item.names.map(name => name || null)))
      sessionStorage.setItem(`mulan:image:${result.image_id}`, JSON.stringify(result)); navigate(`/convert/result/${result.image_id}`)
    } catch (reason) {
      const message = reason instanceof ApiFailure ? reason.message : 'Conversion failed.'
      setError(message)
      if (reason instanceof ApiFailure && typeof reason.details.file === 'string') setBandErrors(Object.fromEntries(bands.filter(item => item.file.name === reason.details.file).map(item => [item.id, message])))
    } finally { setBusy(false) }
  }
  if (!bands.length) return <div className="page tool-page"><div className="page-heading"><span className="eyebrow">Converter</span><h1>BMP bands to multispectral TIFF</h1><p>Order matters: grayscale BMPs contribute one channel and RGB BMPs contribute grouped R, G, B channels.</p></div><UploadDropzone accept=".bmp,image/bmp" multiple title="Drop grayscale or RGB BMP files here" description="Every file must have the same dimensions and a compatible sample datatype." onFiles={add} />{error && <p className="error" role="alert">{error}</p>}</div>
  let outputStart = 0
  return <div className="page tool-page"><div className="page-heading compact"><span className="eyebrow">Converter</span><h1>Arrange your channel groups</h1><p>Drag rows or use the arrow buttons. RGB channels stay together in R, G, B order.</p><p className="conversion-summary" role="status" aria-label="Output channel count"><strong>{outputCount}</strong> output {outputCount === 1 ? 'channel' : 'channels'} from {bands.length} {bands.length === 1 ? 'file' : 'files'}</p></div>
    {error && <p className="error" role="alert">{error}</p>}
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={dragEnd}><SortableContext items={ids} strategy={verticalListSortingStrategy}><div className="band-list">{bands.map((band, index) => { const start = outputStart; outputStart += band.channelCount; return <SortableBand key={band.id} band={band} index={index} count={bands.length} outputStart={start} error={bandErrors[band.id]} onMove={move} onDelete={() => setBands(items => items.filter(item => item.id !== band.id))} onName={(nameIndex, name) => setBands(items => items.map(item => item.id === band.id ? { ...item, names: item.names.map((value, itemIndex) => itemIndex === nameIndex ? name : value) } : item))} /> })}</div></SortableContext></DndContext>
    <div className="action-row"><button className="secondary" onClick={() => addInput.current?.click()}><Plus />Add more bands</button><input ref={addInput} className="visually-hidden" type="file" accept=".bmp,image/bmp" multiple onChange={event => add(Array.from(event.target.files || []))} /><button className="primary large" disabled={busy || !bands.length} onClick={convert}>{busy ? 'Converting…' : 'Convert to TIF'}</button></div>
  </div>
}
