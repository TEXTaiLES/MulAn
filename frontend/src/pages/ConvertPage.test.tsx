import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { ConvertPage } from './ConvertPage'

describe('converter ordering', () => {
  it('adds, labels, reorders, and deletes ordered bands', () => {
    render(<MemoryRouter><ConvertPage /></MemoryRouter>)
    const input = screen.getByLabelText('Drop grayscale BMP bands here')
    const first = new File(['a'], '450.bmp', { type: 'image/bmp' }); const second = new File(['b'], '850.bmp', { type: 'image/bmp' })
    fireEvent.change(input, { target: { files: [first, second] } })
    expect(screen.getByText('450.bmp')).toBeInTheDocument(); expect(screen.getByText('850.bmp')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Move Channel 2 up'))
    const names = screen.getAllByRole('strong').map(element => element.textContent)
    expect(names.slice(0, 2)).toEqual(['850.bmp', '450.bmp'])
    fireEvent.change(screen.getByLabelText('Channel 1 name'), { target: { value: '850nm' } })
    expect(screen.getByDisplayValue('850nm')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Remove 450.bmp'))
    expect(screen.queryByText('450.bmp')).not.toBeInTheDocument()
  })

  it('shows an authoritative server error beside the affected band', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: 'dimension_mismatch', message: 'All BMP images must have identical dimensions.', details: { file: 'bad.bmp' } } }), { status: 422, headers: { 'Content-Type': 'application/json' } })))
    render(<MemoryRouter><ConvertPage /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Drop grayscale BMP bands here'), { target: { files: [new File(['a'], 'good.bmp'), new File(['b'], 'bad.bmp')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Convert to TIF' }))
    expect(await screen.findByText('All BMP images must have identical dimensions.', { selector: '.band-file-error' })).toBeInTheDocument()
  })
})
