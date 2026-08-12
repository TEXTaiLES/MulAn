import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { App } from './App'

describe('global navigation', () => {
  it('shows all features and navigates through the shared shell', () => {
    render(<MemoryRouter initialEntries={['/']}><App /></MemoryRouter>)
    expect(screen.getByRole('heading', { name: 'Convert. Inspect. Annotate.' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: 'Viewer' }))
    expect(screen.getByRole('heading', { name: 'Explore every spectral channel' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /MulAn/ })).toBeInTheDocument()
    expect(screen.getByText('Documentation')).toBeInTheDocument()
  })
})

