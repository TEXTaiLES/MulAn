import { describe, expect, it } from 'vitest'
import { displayToImage, fitTransform } from './coordinates'

describe('coordinate transforms', () => {
  it('maps transformed display coordinates into source pixels', () => {
    expect(displayToImage({ x: 110, y: 70 }, { scale: 2, offsetX: 10, offsetY: 20 }, 100, 80)).toEqual({ x: 50, y: 25 })
  })
  it('fits and centers while preserving aspect ratio', () => {
    expect(fitTransform(1000, 500, 500, 500)).toEqual({ scale: .5, offsetX: 0, offsetY: 125 })
  })
  it('clips pointer coordinates to the source extent', () => {
    expect(displayToImage({ x: -10, y: 1000 }, { scale: 1, offsetX: 0, offsetY: 0 }, 20, 10)).toEqual({ x: 0, y: 9 })
  })
})

