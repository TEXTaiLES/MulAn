import '@testing-library/jest-dom/vitest'
import { createElement } from 'react'
import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

vi.mock('react-konva', () => ({
  Stage: ({ children }: { children: React.ReactNode }) => createElement('div', { 'data-testid': 'stage' }, children),
  Layer: ({ children }: { children: React.ReactNode }) => createElement('div', null, children),
  Image: () => createElement('div'), Line: () => createElement('div'), Rect: () => createElement('div'),
}))

afterEach(() => {
  cleanup()
  sessionStorage.clear()
  history.replaceState({}, '', '/')
  vi.unstubAllGlobals()
})
