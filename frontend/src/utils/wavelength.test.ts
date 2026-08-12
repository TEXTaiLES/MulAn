import { describe, expect, it } from 'vitest'
import { inferWavelengthName } from './wavelength'

describe('wavelength filename inference', () => {
  it.each([
    ['700.bmp', '700nm'],
    ['700nm.bmp', '700nm'],
    ['wavelength_700.bmp', '700nm'],
    ['sample-850_nm.bmp', '850nm'],
    ['wl-450.5.bmp', '450.5nm'],
    ['band_1200_capture.bmp', '1200nm'],
  ])('normalizes an evident wavelength in %s', (filename, expected) => {
    expect(inferWavelengthName(filename)).toBe(expected)
  })

  it.each([
    'sample_42.bmp',
    'capture_2024_08_12.bmp',
    'image123.bmp',
    'channel_2.bmp',
    'wavelength_50.bmp',
    'wavelength_9000.bmp',
  ])('does not infer unrelated or implausible numbers from %s', filename => {
    expect(inferWavelengthName(filename)).toBeNull()
  })
})
