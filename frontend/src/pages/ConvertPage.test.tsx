import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { WithSession } from '../test/session'
import { ConvertPage } from './ConvertPage'

function bmpFile(name: string, bitsPerPixel: number) {
  const bytes = new Uint8Array(54)
  const view = new DataView(bytes.buffer)
  bytes[0] = 0x42; bytes[1] = 0x4d
  view.setUint32(14, 40, true)
  view.setUint16(28, bitsPerPixel, true)
  return new File([bytes], name, { type: 'image/bmp' })
}

describe('converter ordering', () => {
  it('adds, labels, reorders, and deletes ordered grayscale files', async () => {
    render(<WithSession><MemoryRouter><ConvertPage /></MemoryRouter></WithSession>)
    const input = screen.getByLabelText('Drop grayscale or RGB BMP files here')
    const first = new File(['a'], '450.bmp', { type: 'image/bmp' }); const second = new File(['b'], '850.bmp', { type: 'image/bmp' })
    fireEvent.change(input, { target: { files: [first, second] } })
    expect(await screen.findByText('450.bmp')).toBeInTheDocument(); expect(screen.getByText('850.bmp')).toBeInTheDocument()
    expect(screen.getByLabelText('Channel 1 name')).toHaveValue('450nm')
    expect(screen.getByLabelText('Channel 2 name')).toHaveValue('850nm')
    expect(screen.getByLabelText('Output channel count')).toHaveTextContent('2 output channels from 2 files')
    const guide = screen.getByLabelText('Wavelength order: lower to higher')
    expect(guide).toHaveTextContent('Lowerwavelength / nmHigherwavelength / nm')
    expect(guide.querySelector('svg')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Move Channel 2 up'))
    const names = Array.from(document.querySelectorAll('.band-info strong')).map(element => element.textContent)
    expect(names.slice(0, 2)).toEqual(['850.bmp', '450.bmp'])
    fireEvent.change(screen.getByLabelText('Channel 1 name'), { target: { value: '850nm' } })
    expect(screen.getByDisplayValue('850nm')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Remove 450.bmp'))
    expect(screen.queryByText('450.bmp')).not.toBeInTheDocument()
  })

  it('shows RGB contribution, expanded names, total count, and grouped reordering', async () => {
    render(<WithSession><MemoryRouter><ConvertPage /></MemoryRouter></WithSession>)
    fireEvent.change(screen.getByLabelText('Drop grayscale or RGB BMP files here'), { target: { files: [bmpFile('gray.bmp', 8), bmpFile('700nm.bmp', 24)] } })
    expect(await screen.findByText('RGB · 3 channels · 1 KB')).toBeInTheDocument()
    expect(screen.getByText('Grayscale · 1 channel · 1 KB')).toBeInTheDocument()
    expect(screen.getByLabelText('Output channel count')).toHaveTextContent('4 output channels from 2 files')
    expect(screen.getByLabelText('Channel 2 name')).toHaveAttribute('placeholder', 'R name (optional)')
    expect(screen.getByLabelText('Channel 3 name')).toHaveAttribute('placeholder', 'G name (optional)')
    expect(screen.getByLabelText('Channel 4 name')).toHaveAttribute('placeholder', 'B name (optional)')
    expect(screen.getByLabelText('Channel 2 name')).toHaveValue('')
    expect(screen.getByLabelText('Channel 3 name')).toHaveValue('')
    expect(screen.getByLabelText('Channel 4 name')).toHaveValue('')
    fireEvent.change(screen.getByLabelText('Channel 2 name'), { target: { value: 'Visible red' } })
    fireEvent.click(screen.getByLabelText('Move Channel 2 up'))
    const files = Array.from(document.querySelectorAll('.band-info strong')).map(element => element.textContent)
    expect(files.slice(0, 2)).toEqual(['700nm.bmp', 'gray.bmp'])
    expect(screen.getByText('Channels 1–3')).toBeInTheDocument()
    expect(screen.getByLabelText('Channel 1 name')).toHaveValue('Visible red')
  })

  it('infers every incremental grayscale upload without changing edited names', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ image_id: 'converted', filename: 'result.tif', width: 4, height: 4, channel_count: 3, dtype: 'uint8', channel_names: ['red edge custom', '850nm', null], georeferenced: false }), { status: 201, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)
    render(<WithSession><MemoryRouter><ConvertPage /></MemoryRouter></WithSession>)
    fireEvent.change(screen.getByLabelText('Drop grayscale or RGB BMP files here'), { target: { files: [bmpFile('700.bmp', 8)] } })
    expect(await screen.findByLabelText('Channel 1 name')).toHaveValue('700nm')
    fireEvent.change(screen.getByLabelText('Channel 1 name'), { target: { value: 'red edge custom' } })

    fireEvent.change(screen.getByLabelText('Add more BMP files'), { target: { files: [bmpFile('wavelength_850.bmp', 8), bmpFile('capture_12.bmp', 8)] } })

    expect(await screen.findByLabelText('Channel 2 name')).toHaveValue('850nm')
    expect(screen.getByLabelText('Channel 3 name')).toHaveValue('')
    expect(screen.getByLabelText('Channel 1 name')).toHaveValue('red edge custom')

    fireEvent.click(screen.getByRole('button', { name: 'Convert to TIF' }))
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce())
    const form = fetchMock.mock.calls[0][1].body as FormData
    expect(JSON.parse(String(form.get('channel_names')))).toEqual(['red edge custom', '850nm', null])
  })

  it('shows an authoritative server error beside the affected band', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: 'dimension_mismatch', message: 'All BMP images must have identical dimensions.', details: { file: 'bad.bmp' } } }), { status: 422, headers: { 'Content-Type': 'application/json' } })))
    render(<WithSession><MemoryRouter><ConvertPage /></MemoryRouter></WithSession>)
    fireEvent.change(screen.getByLabelText('Drop grayscale or RGB BMP files here'), { target: { files: [new File(['a'], 'good.bmp'), new File(['b'], 'bad.bmp')] } })
    await screen.findByText('good.bmp')
    fireEvent.click(screen.getByRole('button', { name: 'Convert to TIF' }))
    expect(await screen.findByText('All BMP images must have identical dimensions.', { selector: '.band-file-error' })).toBeInTheDocument()
  })

  it('cannot convert without permission to add HESTIA images', async () => {
    const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock)
    render(<WithSession denied={['images_create']}><MemoryRouter><ConvertPage /></MemoryRouter></WithSession>)
    expect(screen.getByRole('status')).toHaveTextContent('cannot add images')
    fireEvent.change(screen.getByLabelText('Drop grayscale or RGB BMP files here'), { target: { files: [bmpFile('450.bmp', 8)] } })
    await screen.findByText('450.bmp')
    expect(screen.getByRole('button', { name: 'Convert to TIF' })).toBeDisabled()
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
