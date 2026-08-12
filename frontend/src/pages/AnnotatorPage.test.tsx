import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { UnsavedProvider, useUnsaved } from '../context/UnsavedContext'
import { AnnotatorPage } from './AnnotatorPage'

vi.mock('react-konva', () => ({ Stage: ({ children }: { children: React.ReactNode }) => <div data-testid="stage">{children}</div>, Layer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, Image: () => <div />, Line: () => <div />, Rect: () => <div /> }))

const image = { image_id: 'image-1', filename: 'sample.tif', width: 20, height: 10, channel_count: 2, dtype: 'uint16', channel_names: [null, null], georeferenced: false }
let annotation = { annotation_id: 'ann-1', image_id: 'image-1', filename: 'sample.tif', width: 20, height: 10, channel_count: 2, revision: 0, saved_revision: 0, classes: [{ id: 0, name: 'Background', description: '', color: '#000000', order: 0, visible: true }], can_undo: false, can_redo: false, statistics: [{ class_id: 0, pixel_count: 200 }] }

function json(value: unknown, status = 200) { return Promise.resolve(new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })) }
function installFetch() {
  vi.stubGlobal('fetch', vi.fn((url: string | URL | Request, init?: RequestInit) => {
    const path = String(url); const method = init?.method || 'GET'
    if (path === '/api/v1/images/image-1') return json(image)
    if (path === '/api/v1/annotations' && method === 'POST') return json(annotation, 201)
    if (path === '/api/v1/annotations/ann-1' && method === 'GET') return json(annotation)
    if (path.endsWith('/classes') && method === 'POST') { const body = JSON.parse(String(init?.body)); const created = { id: 1, ...body, order: 1, visible: true }; annotation = { ...annotation, revision: annotation.revision + 1, classes: [...annotation.classes, created] }; return json(created, 201) }
    if (path.includes('/classes/1') && method === 'PATCH') { const value = { ...annotation.classes[1], ...JSON.parse(String(init?.body)) }; annotation = { ...annotation, revision: annotation.revision + 1, classes: [annotation.classes[0], value] }; return json(value) }
    if (path.includes('/class-order')) { const ids = JSON.parse(String(init?.body)).class_ids as number[]; const classes = ids.map(id => annotation.classes.find(item => item.id === id)!); annotation = { ...annotation, revision: annotation.revision + 1, classes }; return json({ classes }) }
    if (path.includes('/classes/1') && method === 'DELETE') { annotation = { ...annotation, revision: annotation.revision + 1, classes: annotation.classes.filter(item => item.id !== 1) }; return Promise.resolve(new Response(null, { status: 204 })) }
    if (path.endsWith('/save')) { annotation = { ...annotation, saved_revision: annotation.revision }; return json({ revision: annotation.revision, saved_revision: annotation.revision }) }
    if (path.endsWith('/undo')) { annotation = { ...annotation, revision: annotation.revision + 1, can_undo: false, can_redo: true }; return json(annotation) }
    if (path.endsWith('/redo')) { annotation = { ...annotation, revision: annotation.revision + 1, can_undo: true, can_redo: false }; return json(annotation) }
    if (path.endsWith('/mask') && method === 'PUT') {
      const form = init?.body as FormData
      if (form.get('overwrite') === 'false') return json({ error: { code: 'overwrite_required', message: 'Explicit overwrite required' } }, 409)
      annotation = { ...annotation, revision: annotation.revision + 1, can_undo: true, can_redo: false }; return json(annotation)
    }
    return json({})
  }))
}
function DirtyProbe() { const { dirty } = useUnsaved(); return <output aria-label="Dirty state">{dirty ? 'dirty' : 'clean'}</output> }
function view() { return render(<MemoryRouter initialEntries={['/annotator?image_id=image-1']}><UnsavedProvider><DirtyProbe /><Routes><Route path="annotator" element={<AnnotatorPage />} /></Routes></UnsavedProvider></MemoryRouter>) }

describe('annotator class and save state', () => {
  beforeEach(() => { annotation = { annotation_id: 'ann-1', image_id: 'image-1', filename: 'sample.tif', width: 20, height: 10, channel_count: 2, revision: 0, saved_revision: 0, classes: [{ id: 0, name: 'Background', description: '', color: '#000000', order: 0, visible: true }], can_undo: false, can_redo: false, statistics: [{ class_id: 0, pixel_count: 200 }] }; installFetch() })
  afterEach(() => vi.useRealTimers())
  it('creates, edits, reorders, hides, and confirms class deletion without changing IDs', async () => {
    view(); await screen.findByText('Semantic layers'); expect(screen.queryByText('200 px')).not.toBeInTheDocument(); fireEvent.click(screen.getByRole('button', { name: 'Add class' })); const dialog = screen.getByRole('dialog', { name: 'Add class' }); fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'Vegetation' } }); fireEvent.click(within(dialog).getByRole('button', { name: 'Add class' }))
    await screen.findByText('Vegetation'); expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByLabelText('Move Vegetation up').querySelector('.lucide-arrow-up')).toBeInTheDocument()
    expect(screen.getByLabelText('Move Vegetation down').querySelector('.lucide-arrow-down')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Edit Vegetation')); fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Healthy' } }); fireEvent.click(screen.getByRole('button', { name: 'Save class' })); await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    fireEvent.click(screen.getByLabelText('Hide Vegetation')); await waitFor(() => expect(screen.getByLabelText('Show Vegetation')).toBeInTheDocument())
    fireEvent.click(screen.getByLabelText('Move Vegetation up')); await waitFor(() => expect(annotation.classes[0].id).toBe(1)); expect(screen.getByLabelText('Show Vegetation')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Delete Vegetation')); expect(screen.getByRole('dialog', { name: /Delete/ })).toBeInTheDocument(); expect((fetch as ReturnType<typeof vi.fn>).mock.calls.some(call => String(call[0]).includes('/classes/1') && call[1]?.method === 'DELETE')).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Delete' })); await waitFor(() => expect(screen.queryByText('Vegetation')).not.toBeInTheDocument())
  })
  it('requires overwrite confirmation and opens the save export dialog', async () => {
    annotation = { ...annotation, revision: 2, saved_revision: 0 }; view(); await screen.findByText('Semantic layers'); await waitFor(() => expect(screen.getByLabelText('Dirty state')).toHaveTextContent('dirty'))
    const mask = new File(['mask'], 'mask.tif', { type: 'image/tiff' }); const panel = screen.getByText('Semantic layers').closest('aside')!; fireEvent.drop(panel, { dataTransfer: { files: [mask] } })
    await screen.findByRole('dialog', { name: 'Replace current annotations?' }); fireEvent.click(screen.getByRole('button', { name: 'Replace' })); await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' })); await screen.findByRole('dialog', { name: 'Annotation saved' }); await waitFor(() => expect(screen.getByLabelText('Dirty state')).toHaveTextContent('clean')); expect(screen.getByRole('link', { name: 'Download Mask' })).toBeInTheDocument(); expect(screen.getByRole('link', { name: 'Download Image + Mask' })).toBeInTheDocument()
  })

  it('uses centralized tool shortcuts, shows shortcut tooltips, and ignores editable targets', async () => {
    view(); await screen.findByText('Semantic layers')
    expect(screen.getByLabelText('Brush')).toHaveAttribute('title', 'Brush (B)')
    expect(screen.getByLabelText('Brush')).toHaveAttribute('aria-keyshortcuts', 'B')
    expect(screen.getByLabelText('Lasso Subtract')).toHaveAttribute('title', 'Lasso Subtract (Shift+L)')

    fireEvent.keyDown(window, { key: 'h' })
    expect(screen.getByLabelText('Pan')).toHaveClass('active')
    fireEvent.keyDown(window, { key: 'L', shiftKey: true })
    expect(screen.getByLabelText('Lasso Subtract')).toHaveClass('active')

    fireEvent.click(screen.getByRole('button', { name: 'Add class' }))
    const nameInput = screen.getByRole('dialog', { name: 'Add class' }).querySelector('input')!
    fireEvent.keyDown(nameInput, { key: 'r' })
    expect(screen.getByLabelText('Lasso Subtract')).toHaveClass('active')

    const editable = document.createElement('div'); editable.setAttribute('contenteditable', 'true'); document.body.append(editable)
    fireEvent.keyDown(editable, { key: 'b' })
    expect(screen.getByLabelText('Lasso Subtract')).toHaveClass('active')
    editable.remove()
  })

  it('routes Apply Mask through shared undo and redo controls', async () => {
    annotation = { ...annotation, revision: 2, saved_revision: 0 }
    view(); await screen.findByText('Semantic layers')
    const mask = new File(['mask'], 'mask.tif', { type: 'image/tiff' })
    fireEvent.change(screen.getByLabelText('Apply Mask file'), { target: { files: [mask] } })
    await screen.findByRole('dialog', { name: 'Replace current annotations?' })
    fireEvent.click(screen.getByRole('button', { name: 'Replace' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Undo' })).toBeEnabled())

    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Redo' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Redo' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Redo' })).toBeDisabled())
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls.some(call => String(call[0]).endsWith('/undo'))).toBe(true)
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls.some(call => String(call[0]).endsWith('/redo'))).toBe(true)
  })

  it('auto-dismisses transient alerts but keeps confirmation dialogs open', async () => {
    annotation = { ...annotation, revision: 2, saved_revision: 0 }
    view(); await screen.findByText('Semantic layers')
    vi.useFakeTimers()
    fireEvent.change(screen.getByLabelText('Apply Mask file'), { target: { files: [new File(['x'], 'notes.txt')] } })
    expect(screen.getByRole('alert')).toHaveTextContent('Select mask.tif or an annotation ZIP package.')
    act(() => vi.advanceTimersByTime(4000))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    vi.useRealTimers()

    fireEvent.change(screen.getByLabelText('Apply Mask file'), { target: { files: [new File(['mask'], 'mask.tif')] } })
    await screen.findByRole('dialog', { name: 'Replace current annotations?' })
    vi.useFakeTimers()
    act(() => vi.advanceTimersByTime(10000))
    expect(screen.getByRole('dialog', { name: 'Replace current annotations?' })).toBeInTheDocument()
  })
})
