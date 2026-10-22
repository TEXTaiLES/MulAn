import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { AnnotatorPage } from '../pages/AnnotatorPage'
import { ViewerPage } from '../pages/ViewerPage'
import { WithSession } from '../test/session'
import type { Capability } from '../types'
import { ImageLibrary } from './ImageLibrary'

const image = (id: number, extra = {}) => ({ image_id: `image-${id}`, filename: `scan-${id}.tif`, width: 20, height: 10, channel_count: 3, dtype: 'uint16', channel_names: [null, null, null], georeferenced: false, has_annotation: false, created_at: '2026-10-01T09:00:00Z', created_by: { id: 'user-2', display_name: 'Bob Builder' }, ...extra })
function respond(value: unknown, status = 200) { return Promise.resolve(new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })) }
function stubImages(total = 2) { const fetchMock = vi.fn((url: string) => { const query = new URL(String(url), 'http://mulan.test').searchParams; const page = Number(query.get('page')); return respond({ items: [image(page * 10 + 1, { has_annotation: true }), image(page * 10 + 2)], page, per_page: Number(query.get('per_page')), total }) }); vi.stubGlobal('fetch', fetchMock); return fetchMock }
function libraryView(onOpen = vi.fn(), denied: Capability[] = []) { render(<WithSession denied={denied}><ImageLibrary actionLabel="View" onOpen={onOpen} /></WithSession>); return onOpen }

describe('HESTIA image library', () => {
  it('lists HESTIA images with their annotation state and opens the chosen one', async () => {
    stubImages(); const onOpen = libraryView()
    expect(await screen.findByText('scan-11.tif')).toBeInTheDocument()
    expect(screen.getAllByText('Annotated')).toHaveLength(1)
    expect(screen.getAllByText(/Bob Builder/)).toHaveLength(2)
    fireEvent.click(screen.getByRole('button', { name: 'View scan-12.tif' }))
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ image_id: 'image-12' }))
  })

  it('searches by filename and pages through results', async () => {
    const fetchMock = stubImages(30); libraryView()
    await screen.findByText('Page 1 of 3')
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    expect(await screen.findByText('scan-21.tif')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Search images by filename'), { target: { value: ' warp ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    await waitFor(() => expect(String(fetchMock.mock.calls.at(-1)?.[0])).toBe('/api/v1/images?page=1&per_page=12&q=warp'))
  })

  it('explains missing HESTIA image access without calling the API', () => {
    const fetchMock = stubImages(); libraryView(vi.fn(), ['images_read'])
    expect(screen.getByRole('status')).toHaveTextContent('does not have access to multispectral images')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('offers uploads only to accounts that may add HESTIA images', async () => {
    stubImages()
    const { unmount } = render(<WithSession><MemoryRouter initialEntries={['/viewer']}><Routes><Route path="viewer" element={<ViewerPage />} /></Routes></MemoryRouter></WithSession>)
    expect(await screen.findByLabelText('Drop a multispectral TIFF here')).toBeInTheDocument(); unmount()
    render(<WithSession denied={['images_create']}><MemoryRouter initialEntries={['/annotator']}><Routes><Route path="annotator" element={<AnnotatorPage />} /></Routes></MemoryRouter></WithSession>)
    expect(await screen.findByText('scan-11.tif')).toBeInTheDocument()
    expect(screen.queryByLabelText('Drop a multispectral TIFF here')).not.toBeInTheDocument()
  })
})
