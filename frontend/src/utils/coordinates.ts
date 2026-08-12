export interface ViewTransform { scale: number; offsetX: number; offsetY: number }
export interface Point { x: number; y: number }

export function displayToImage(point: Point, transform: ViewTransform, width: number, height: number): Point {
  if (!Number.isFinite(transform.scale) || transform.scale <= 0) throw new Error('Scale must be positive')
  return {
    x: Math.max(0, Math.min(width - 1, (point.x - transform.offsetX) / transform.scale)),
    y: Math.max(0, Math.min(height - 1, (point.y - transform.offsetY) / transform.scale)),
  }
}

export function fitTransform(imageWidth: number, imageHeight: number, viewportWidth: number, viewportHeight: number): ViewTransform {
  const scale = Math.min(viewportWidth / imageWidth, viewportHeight / imageHeight)
  return { scale, offsetX: (viewportWidth - imageWidth * scale) / 2, offsetY: (viewportHeight - imageHeight * scale) / 2 }
}

