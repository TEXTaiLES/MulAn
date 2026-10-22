import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { WithSession } from '../test/session'
import { ViewerPage } from './ViewerPage'

const image = { image_id: 'image-1', filename: 'sample.tif', width: 20, height: 10, channel_count: 3, dtype: 'uint16', channel_names: ['450nm', null, '850nm'], georeferenced: false }

describe('viewer controls', () => {
  beforeEach(() => { vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(new Response(JSON.stringify(String(url).startsWith('/api/v1/images?') ? { items: [], page: 1, per_page: 12, total: 0 } : image), { status: 200, headers: { 'Content-Type': 'application/json' } })))) })
  it('navigates channels, toggles grid, selects a tile, and transfers the image ID', async () => {
    render(<WithSession><MemoryRouter initialEntries={['/viewer?image_id=image-1']}><Routes><Route path="viewer" element={<ViewerPage />} /><Route path="annotator" element={<p>Annotator destination</p>} /></Routes></MemoryRouter></WithSession>)
    await screen.findByRole('heading', { name: 'sample.tif' })
    fireEvent.click(screen.getByRole('button', { name: 'Zoom in' })); expect(screen.getByAltText('Channel 1').closest('.image-viewport')).toHaveClass('pannable')
    fireEvent.click(screen.getByRole('button', { name: 'Next channel' })); expect(screen.getByText('Channel 2 / 3')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Grid/ })); expect(screen.getAllByRole('button', { name: /^Channel [123]/ })).toHaveLength(3)
    fireEvent.click(screen.getByRole('button', { name: /Channel 3.*850nm/ })); expect(screen.getByText('Channel 3 / 3')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Open in Annotator' })); await waitFor(() => expect(screen.getByText('Annotator destination')).toBeInTheDocument())
  })

  it('hides the annotator hand-off without HESTIA annotation access', async () => {
    render(<WithSession denied={['annotations_read']}><MemoryRouter initialEntries={['/viewer?image_id=image-1']}><Routes><Route path="viewer" element={<ViewerPage />} /></Routes></MemoryRouter></WithSession>)
    await screen.findByRole('heading', { name: 'sample.tif' })
    expect(screen.queryByRole('button', { name: 'Open in Annotator' })).not.toBeInTheDocument()
  })
})
