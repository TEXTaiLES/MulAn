const PLAUSIBLE_MIN_NM = 100
const PLAUSIBLE_MAX_NM = 2500

function normalize(candidate: string | undefined): string | null {
  if (!candidate) return null
  const value = Number(candidate)
  if (!Number.isFinite(value) || value < PLAUSIBLE_MIN_NM || value > PLAUSIBLE_MAX_NM) return null
  return `${value}nm`
}

export function inferWavelengthName(filename: string): string | null {
  const stem = filename.replace(/\.bmp$/i, '')
  const exact = stem.match(/^\s*(\d{3,4}(?:\.\d+)?)\s*$/)
  if (exact) return normalize(exact[1])

  const unit = stem.match(/(?:^|[^a-z0-9])(\d{3,4}(?:\.\d+)?)[_\-\s]*nm(?=$|[^a-z0-9])/i)
  if (unit) return normalize(unit[1])

  const labeled = stem.match(/(?:^|[^a-z0-9])(?:wavelength|wave|lambda|wl|band)[_\-\s]*(\d{3,4}(?:\.\d+)?)(?=$|[^0-9])/i)
  return normalize(labeled?.[1])
}
