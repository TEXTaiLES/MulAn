import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { signIn } from './api/client'
import { App } from './App'
import { testSession } from './test/session'

vi.mock('./api/client', async importOriginal => ({ ...await importOriginal<typeof import('./api/client')>(), signIn: vi.fn() }))

function respond(value: unknown, status = 200) { return Promise.resolve(new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })) }
function stubSession(value: unknown, status = 200) { vi.stubGlobal('fetch', vi.fn((url: string) => String(url) === '/api/v1/session' ? respond(value, status) : respond({ items: [], page: 1, per_page: 24, total: 0 }))) }

describe('global navigation', () => {
  beforeEach(() => vi.mocked(signIn).mockClear())

  it('shows all features, the signed-in HESTIA user, and navigates through the shared shell', async () => {
    stubSession(testSession())
    render(<MemoryRouter initialEntries={['/']}><App /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: 'MulAn: Multispectral Image Viewer and Annotator' })).toBeInTheDocument()
    expect(screen.getByText('Ada Lovelace')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Sign out' })).toHaveAttribute('href', '/auth/logout')
    fireEvent.click(screen.getByRole('link', { name: 'Viewer' }))
    expect(screen.getByRole('heading', { name: 'View multispectral TIFF channels' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /MulAn/ })).toBeInTheDocument()
    expect(screen.getByText('Documentation')).toBeInTheDocument()
  })

  it('sends signed-out users to the HESTIA sign-in page', async () => {
    stubSession({ ...testSession(), authenticated: false, user: null })
    render(<MemoryRouter initialEntries={['/annotator']}><App /></MemoryRouter>)
    expect(await screen.findByText('Redirecting to the HESTIA sign-in page…')).toBeInTheDocument()
    expect(signIn).toHaveBeenCalledWith('/auth/login')
    expect(screen.queryByRole('link', { name: 'Viewer' })).not.toBeInTheDocument()
  })

  it('explains when HESTIA is unavailable', async () => {
    stubSession({ error: { code: 'hestia_unavailable', message: 'HESTIA could not be reached.', details: {} } }, 502)
    render(<MemoryRouter><App /></MemoryRouter>)
    expect(await screen.findByRole('alert')).toHaveTextContent('HESTIA could not be reached.')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})
