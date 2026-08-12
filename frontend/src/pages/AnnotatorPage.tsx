import { Brush, CircleOff, Download, Eye, EyeOff, GripVertical, Hand, MousePointer2, Pencil, Redo2, Save, Square, Trash2, Undo2, Upload, ZoomIn, ZoomOut } from 'lucide-react'
import { closestCenter, DndContext, KeyboardSensor, PointerSensor, type DragEndEvent, useSensor, useSensors } from '@dnd-kit/core'
import { SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Image as KonvaImage, Layer, Line, Rect, Stage } from 'react-konva'
import { useSearchParams } from 'react-router-dom'
import type Konva from 'konva'
import { api, ApiFailure } from '../api/client'
import { Dialog } from '../components/Dialog'
import { ImageControls } from '../components/ImageControls'
import { UploadDropzone } from '../components/UploadDropzone'
import { useUnsaved } from '../context/UnsavedContext'
import type { AnnotationClass, AnnotationResource, ImageResource } from '../types'
import { displayToImage, fitTransform, type Point, type ViewTransform } from '../utils/coordinates'

type Tool = 'pan' | 'brush_add' | 'erase' | 'lasso_add' | 'lasso_subtract' | 'rectangle_add' | 'rectangle_subtract'
const toolItems: { id: Tool; label: string; icon: typeof Brush }[] = [
  { id: 'pan', label: 'Pan', icon: Hand },
  { id: 'brush_add', label: 'Brush', icon: Brush }, { id: 'erase', label: 'Eraser', icon: CircleOff },
  { id: 'lasso_add', label: 'Lasso Add', icon: MousePointer2 }, { id: 'lasso_subtract', label: 'Lasso Subtract', icon: MousePointer2 },
  { id: 'rectangle_add', label: 'Rectangle Add', icon: Square }, { id: 'rectangle_subtract', label: 'Rectangle Subtract', icon: Square },
]

function useRemoteImage(url: string | null) {
  const [image, setImage] = useState<HTMLImageElement | null>(null)
  useEffect(() => { if (!url) { setImage(null); return }; const next = new window.Image(); next.onload = () => setImage(next); next.src = url; return () => { next.onload = null } }, [url])
  return image
}

function ClassDialog({ existing, onClose, onSubmit }: { existing?: AnnotationClass; onClose: () => void; onSubmit: (value: Pick<AnnotationClass, 'name' | 'description' | 'color'>) => void }) {
  const [name, setName] = useState(existing?.name || ''); const [description, setDescription] = useState(existing?.description || ''); const [color, setColor] = useState(existing?.color || '#735FA4')
  return <Dialog title={existing ? `Edit ${existing.name}` : 'Add class'} onClose={onClose}><label>Name<input autoFocus value={name} onChange={event => setName(event.target.value)} /></label><label>Description<textarea value={description} onChange={event => setDescription(event.target.value)} /></label><label>Display color<input type="color" value={color} onChange={event => setColor(event.target.value)} /></label><div className="dialog-actions"><button onClick={onClose}>Cancel</button><button className="primary" disabled={!name.trim()} onClick={() => onSubmit({ name: name.trim(), description, color })}>{existing ? 'Save class' : 'Add class'}</button></div></Dialog>
}

function SortableClassRow({ item, index, count, active, pixelCount, onSelect, onToggle, onEdit, onMove, onDelete }: { item: AnnotationClass; index: number; count: number; active: boolean; pixelCount: number; onSelect: () => void; onToggle: () => void; onEdit: () => void; onMove: (change: number) => void; onDelete: () => void }) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: item.id })
  return <div ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition }} className={`class-row ${active ? 'active' : ''}`} onClick={onSelect}>
    <button className="class-grip" title={`Drag ${item.name}`} aria-label={`Drag ${item.name}`} {...attributes} {...listeners}><GripVertical /></button>
    <span className="swatch" style={{ background: item.color }} /><span className="class-id">{item.id}</span><span className="class-name">{item.name}<small>{pixelCount} px</small></span>
    <button title={item.visible === false ? 'Show class' : 'Hide class'} aria-label={`${item.visible === false ? 'Show' : 'Hide'} ${item.name}`} onClick={event => { event.stopPropagation(); onToggle() }}>{item.visible === false ? <EyeOff /> : <Eye />}</button>
    <button title="Edit class" aria-label={`Edit ${item.name}`} onClick={event => { event.stopPropagation(); onEdit() }}><Pencil /></button>
    <button title="Move class up" aria-label={`Move ${item.name} up`} disabled={index === 0} onClick={event => { event.stopPropagation(); onMove(-1) }}><ZoomIn className="rotate-icon" /></button>
    <button title="Move class down" aria-label={`Move ${item.name} down`} disabled={index === count - 1} onClick={event => { event.stopPropagation(); onMove(1) }}><ZoomOut className="rotate-icon" /></button>
    <button title="Delete class" aria-label={`Delete ${item.name}`} disabled={item.id === 0} onClick={event => { event.stopPropagation(); onDelete() }}><Trash2 /></button>
  </div>
}

export function AnnotatorPage() {
  const [params] = useSearchParams(); const requestedImage = params.get('image_id'); const [image, setImage] = useState<ImageResource | null>(null); const [annotation, setAnnotation] = useState<AnnotationResource | null>(null); const [channel, setChannel] = useState(0); const [tool, setTool] = useState<Tool>('brush_add'); const [activeClass, setActiveClass] = useState(0); const [radius, setRadius] = useState(12); const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const [editClass, setEditClass] = useState<AnnotationClass | 'new' | null>(null); const [deleteClass, setDeleteClass] = useState<AnnotationClass | null>(null); const [pendingMask, setPendingMask] = useState<File[] | null>(null); const [showExport, setShowExport] = useState(false); const [overlayVersion, setOverlayVersion] = useState(0); const maskInput = useRef<HTMLInputElement>(null); const initializedImage = useRef<string | null>(null); const { setDirty } = useUnsaved()
  const canvasWidth = 900, canvasHeight = 610
  const [transform, setTransform] = useState<ViewTransform>({ scale: 1, offsetX: 0, offsetY: 0 }); const [drawing, setDrawing] = useState<Point[]>([])
  const classSensors = useSensors(useSensor(PointerSensor), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }))
  const isDirty = Boolean(annotation && annotation.revision !== annotation.saved_revision)
  const visibleIds = useMemo(() => annotation?.classes.filter(item => item.visible !== false).map(item => item.id) || [], [annotation?.classes])
  const background = useRemoteImage(image ? `/api/v1/images/${image.image_id}/channels/${channel}/preview?max_size=1600` : null)
  const overlay = useRemoteImage(annotation ? `/api/internal/v1/annotations/${annotation.annotation_id}/overlay?max_size=1600&visible_ids=${visibleIds.join(',')}&v=${overlayVersion}` : null)

  const refresh = useCallback(async (id: string) => { const value = await api.annotation(id); setAnnotation(current => ({ ...value, classes: value.classes.map(item => ({ ...item, visible: current?.classes.find(existing => existing.id === item.id)?.visible ?? true })) })); setActiveClass(current => value.classes.some(item => item.id === current && current !== 0) ? current : (value.classes.find(item => item.id !== 0)?.id || 0)); setDirty(value.revision !== value.saved_revision) }, [setDirty])
  const establish = useCallback(async (resource: ImageResource) => {
    setImage(resource); const storedId = sessionStorage.getItem(`mulan:annotation:${resource.image_id}`)
    if (storedId) { try { const existing = await api.annotation(storedId); setAnnotation(existing); setActiveClass(existing.classes.find(item => item.id !== 0)?.id || 0); setDirty(existing.revision !== existing.saved_revision); return } catch { sessionStorage.removeItem(`mulan:annotation:${resource.image_id}`) } }
    const created = await api.createAnnotation(resource.image_id); setAnnotation(created); sessionStorage.setItem(`mulan:annotation:${resource.image_id}`, created.annotation_id); setDirty(false)
  }, [setDirty])
  useEffect(() => { if (requestedImage && initializedImage.current !== requestedImage) { initializedImage.current = requestedImage; setBusy(true); api.image(requestedImage).then(establish).catch(reason => { initializedImage.current = null; setError(reason.message) }).finally(() => setBusy(false)) } }, [requestedImage, establish])
  useEffect(() => { if (image) setTransform(fitTransform(image.width, image.height, canvasWidth, canvasHeight)) }, [image])
  useEffect(() => { setDirty(isDirty) }, [isDirty, setDirty])
  useEffect(() => () => setDirty(false), [setDirty])
  useEffect(() => { const before = (event: BeforeUnloadEvent) => { if (isDirty) { event.preventDefault(); event.returnValue = '' } }; window.addEventListener('beforeunload', before); return () => window.removeEventListener('beforeunload', before) }, [isDirty])

  const uploadImage = async ([file]: File[]) => { if (!file || !/\.tiff?$/i.test(file.name)) { setError('Select a .tif or .tiff file.'); return }; setBusy(true); setError(''); try { await establish(await api.uploadImage(file)) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Upload failed.') } finally { setBusy(false) } }
  const updateRevision = (value: Partial<AnnotationResource>) => { setAnnotation(current => current ? { ...current, ...value } : current); if (value.revision !== undefined && annotation) setDirty(value.revision !== (value.saved_revision ?? annotation.saved_revision)); setOverlayVersion(value => value + 1) }
  const history = async (action: 'undo' | 'redo') => { if (!annotation) return; try { updateRevision(await api.history(annotation.annotation_id, action)) } catch (reason) { setError(reason instanceof Error ? reason.message : 'History operation failed.') } }
  const pointer = (stage: Konva.Stage): Point | null => { const value = stage.getPointerPosition(); return value && image ? displayToImage(value, transform, image.width, image.height) : null }
  const onDown = (event: Konva.KonvaEventObject<PointerEvent>) => { if (tool === 'pan') return; if (!activeClass) { setError('Add or select a non-background class before drawing.'); return }; const point = pointer(event.target.getStage()!); if (point) setDrawing([point]) }
  const onMove = (event: Konva.KonvaEventObject<PointerEvent>) => { if (!drawing.length) return; const point = pointer(event.target.getStage()!); if (point) setDrawing(current => [...current, point]) }
  const onUp = async (event: Konva.KonvaEventObject<PointerEvent>) => {
    if (!annotation || !drawing.length) return; const last = pointer(event.target.getStage()!); let points = last ? [...drawing, last] : drawing
    if (tool.startsWith('rectangle')) points = [drawing[0], points[points.length - 1]]
    setDrawing([]); if (tool.startsWith('lasso') && points.length < 3) return
    try { updateRevision(await api.operation(annotation.annotation_id, { base_revision: annotation.revision, tool, class_id: activeClass, radius, points })) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Drawing operation failed.'); await refresh(annotation.annotation_id) }
  }
  const fit = () => image && setTransform(fitTransform(image.width, image.height, canvasWidth, canvasHeight)); const zoom = (factor: number) => setTransform(value => ({ ...value, scale: Math.max(.05, Math.min(20, value.scale * factor)), offsetX: canvasWidth / 2 - (canvasWidth / 2 - value.offsetX) * factor, offsetY: canvasHeight / 2 - (canvasHeight / 2 - value.offsetY) * factor }))
  const classSubmit = async (value: Pick<AnnotationClass, 'name' | 'description' | 'color'>) => { if (!annotation || !editClass) return; try { if (editClass === 'new') await api.addClass(annotation.annotation_id, value); else await api.editClass(annotation.annotation_id, editClass.id, value); setEditClass(null); await refresh(annotation.annotation_id) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Class update failed.') } }
  const removeClass = async () => { if (!annotation || !deleteClass) return; try { await api.deleteClass(annotation.annotation_id, deleteClass.id); setDeleteClass(null); await refresh(annotation.annotation_id); setOverlayVersion(value => value + 1) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not delete class.') } }
  const moveClass = async (index: number, change: number) => { if (!annotation) return; const items = [...annotation.classes]; const [item] = items.splice(index, 1); items.splice(index + change, 0, item); try { const result = await api.reorderClasses(annotation.annotation_id, items.map(value => value.id)); setAnnotation(current => current ? { ...current, classes: result.classes.map(value => ({ ...value, visible: current.classes.find(existing => existing.id === value.id)?.visible ?? true })), revision: current.revision + 1 } : current); setDirty(true) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not reorder classes.') } }
  const classDragEnd = ({ active, over }: DragEndEvent) => { if (!annotation || !over || active.id === over.id) return; const from = annotation.classes.findIndex(item => item.id === active.id); const to = annotation.classes.findIndex(item => item.id === over.id); if (from >= 0 && to >= 0) void moveClass(from, to - from) }
  const toggleVisibility = (item: AnnotationClass) => { setAnnotation(current => current ? { ...current, classes: current.classes.map(value => value.id === item.id ? { ...value, visible: value.visible === false } : value) } : current); setOverlayVersion(value => value + 1) }
  const importMask = async (files: File[], overwrite = false) => { if (!annotation) return; if (!files.some(file => /\.(tif|tiff|zip)$/i.test(file.name))) { setError('Select mask.tif or an annotation ZIP package.'); return }; try { const updated = await api.replaceMask(annotation.annotation_id, files, overwrite); setAnnotation(updated); setDirty(true); setPendingMask(null); setOverlayVersion(value => value + 1) } catch (reason) { if (reason instanceof ApiFailure && reason.code === 'overwrite_required') setPendingMask(files); else setError(reason instanceof Error ? reason.message : 'Mask import failed.') } }
  const save = async () => { if (!annotation) return; try { const result = await api.save(annotation.annotation_id); updateRevision(result); setDirty(false); setShowExport(true) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Save failed.') } }

  if (!image || !annotation) return <div className="page tool-page"><div className="page-heading"><span className="eyebrow">Annotator</span><h1>Create a semantic segmentation mask</h1><p>Annotations are stored as one integer class ID per source pixel.</p></div>{busy ? <p className="loading">Preparing annotator…</p> : <UploadDropzone accept=".tif,.tiff,image/tiff" title="Drop a multispectral TIFF here" description="The original raster remains unchanged while you annotate." onFiles={uploadImage} />}{error && <p className="error" role="alert">{error}</p>}</div>

  const currentColor = annotation.classes.find(item => item.id === activeClass)?.color || '#E53935'
  const previewPoints = drawing.flatMap(point => [point.x, point.y])
  return <div className="annotator-page">
    <div className="annotator-title"><div><span className="eyebrow">Annotator</span><strong>{image.filename}</strong><span>{image.width} × {image.height}</span></div><ImageControls channel={channel} count={image.channel_count} onChannel={setChannel} onZoom={zoom} onFit={fit} /></div>
    {error && <p className="error annotator-error" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError('')}>×</button></p>}
    <div className="annotator-workspace">
      <aside className="tool-rail" aria-label="Annotation tools">{toolItems.map(item => <button key={item.id} title={item.label} aria-label={item.label} className={tool === item.id ? 'active' : ''} onClick={() => setTool(item.id)}><item.icon /></button>)}<span className="rail-divider" /><button title="Undo" aria-label="Undo" disabled={!annotation.can_undo} onClick={() => history('undo')}><Undo2 /></button><button title="Redo" aria-label="Redo" disabled={!annotation.can_redo} onClick={() => history('redo')}><Redo2 /></button><label className="radius-control" title="Brush radius"><span>{radius}px</span><input aria-label="Brush radius" type="range" min="1" max="80" value={radius} onChange={event => setRadius(Number(event.target.value))} /></label></aside>
      <section className="annotation-canvas"><Stage width={canvasWidth} height={canvasHeight} draggable={tool === 'pan'} onDragEnd={event => { setTransform(value => ({ ...value, offsetX: value.offsetX + event.target.x(), offsetY: value.offsetY + event.target.y() })); event.target.position({ x: 0, y: 0 }) }} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerLeave={onUp}><Layer x={transform.offsetX} y={transform.offsetY} scaleX={transform.scale} scaleY={transform.scale}><KonvaImage image={background || undefined} width={image.width} height={image.height} /><KonvaImage image={overlay || undefined} width={image.width} height={image.height} listening={false} />{drawing.length > 0 && (tool.startsWith('rectangle') ? <Rect x={drawing[0].x} y={drawing[0].y} width={(drawing.at(-1)?.x || drawing[0].x) - drawing[0].x} height={(drawing.at(-1)?.y || drawing[0].y) - drawing[0].y} fill={`${currentColor}55`} stroke={currentColor} strokeWidth={2 / transform.scale} listening={false} /> : <Line points={previewPoints} stroke={tool === 'erase' || tool.endsWith('subtract') ? '#ffffff' : currentColor} strokeWidth={(tool.startsWith('brush') || tool === 'erase' ? radius * 2 : 2 / transform.scale)} closed={tool.startsWith('lasso')} fill={tool.startsWith('lasso') ? `${currentColor}55` : undefined} lineCap="round" lineJoin="round" listening={false} />)}</Layer></Stage></section>
      <aside className="layer-panel" onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); void importMask(Array.from(event.dataTransfer.files)) }}>
        <button className="secondary full" title="Select or drop a mask package" onClick={() => maskInput.current?.click()}><Upload />Apply Mask</button>
        <input ref={maskInput} aria-label="Apply Mask file" className="visually-hidden" type="file" accept=".tif,.tiff,.json,.zip" multiple onChange={event => importMask(Array.from(event.target.files || []))} />
        <div className="panel-heading"><div><span className="eyebrow">Classes</span><h2>Semantic layers</h2></div><button className="primary small" onClick={() => setEditClass('new')}>Add class</button></div>
        <DndContext sensors={classSensors} collisionDetection={closestCenter} onDragEnd={classDragEnd}>
          <SortableContext items={annotation.classes.map(item => item.id)} strategy={verticalListSortingStrategy}>
            <div className="class-list">{annotation.classes.map((item, index) => <SortableClassRow key={item.id} item={item} index={index} count={annotation.classes.length} active={activeClass === item.id} pixelCount={annotation.statistics?.find(value => value.class_id === item.id)?.pixel_count ?? 0} onSelect={() => item.id !== 0 && setActiveClass(item.id)} onToggle={() => toggleVisibility(item)} onEdit={() => setEditClass(item)} onMove={change => moveClass(index, change)} onDelete={() => setDeleteClass(item)} />)}</div>
          </SortableContext>
        </DndContext>
        <button className="primary full save-button" onClick={save}><Save />Save changes</button><small className="revision">Revision {annotation.revision} · {annotation.revision === annotation.saved_revision ? 'Saved' : 'Unsaved changes'}</small>
      </aside>
    </div>
    {editClass && <ClassDialog existing={editClass === 'new' ? undefined : editClass} onClose={() => setEditClass(null)} onSubmit={classSubmit} />}
    {deleteClass && <Dialog title={`Delete “${deleteClass.name}”?`} onClose={() => setDeleteClass(null)}><p>All pixels assigned to this class will become Background.</p><div className="dialog-actions"><button onClick={() => setDeleteClass(null)}>Cancel</button><button className="danger" onClick={removeClass}>Delete</button></div></Dialog>}
    {pendingMask && <Dialog title="Replace current annotations?" onClose={() => setPendingMask(null)}><p>The imported mask will replace the current semantic segmentation. Existing edits may be lost.</p><div className="dialog-actions"><button onClick={() => setPendingMask(null)}>Cancel</button><button className="danger" onClick={() => importMask(pendingMask, true)}>Replace</button></div></Dialog>}
    {showExport && <Dialog title="Annotation saved" onClose={() => setShowExport(false)}><p>Revision {annotation.revision} is saved. Choose an export package.</p><div className="export-actions"><a className="primary button-link" href={`/api/v1/annotations/${annotation.annotation_id}/export?include_image=false`} download><Download />Download Mask</a><a className="secondary button-link" href={`/api/v1/annotations/${annotation.annotation_id}/export?include_image=true`} download><Download />Download Image + Mask</a></div></Dialog>}
  </div>
}
