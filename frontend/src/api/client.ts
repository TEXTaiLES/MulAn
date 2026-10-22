import type { AnnotationClass, AnnotationResource, HestiaSession, ImagePage, ImageResource } from '../types'

export class ApiFailure extends Error {
  code: string
  status: number
  details: Record<string, unknown>
  constructor(message: string, code = 'request_failed', status = 0, details: Record<string, unknown> = {}) {
    super(message)
    this.code = code
    this.status = status
    this.details = details
  }
}

/** Sends the browser to the HESTIA portal; it returns the user to MulAn's front page. */
export function signIn(loginUrl = '/auth/login') { window.location.assign(loginUrl) }

async function parse<T>(response: Response): Promise<T> {
  if (response.status === 401) signIn()
  if (!response.ok) {
    let body: { error?: { code?: string; message?: string; details?: Record<string, unknown> } } = {}
    try { body = await response.json() } catch { /* response was not JSON */ }
    throw new ApiFailure(body.error?.message || `Request failed (${response.status})`, body.error?.code, response.status, body.error?.details)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  session: () => fetch('/api/v1/session').then(parse<HestiaSession>),
  images: ({ page, per_page, q }: { page: number; per_page: number; q?: string }) => {
    const query = new URLSearchParams({ page: String(page), per_page: String(per_page) }); if (q) query.set('q', q)
    return fetch(`/api/v1/images?${query}`).then(parse<ImagePage>)
  },
  image: (id: string) => fetch(`/api/v1/images/${id}`).then(parse<ImageResource>),
  uploadImage: (file: File) => {
    const data = new FormData(); data.append('file', file)
    return fetch('/api/v1/images', { method: 'POST', body: data }).then(parse<ImageResource>)
  },
  convert: (files: File[], channelNames?: (string | null)[], outputName = 'multispectral.tif') => {
    const data = new FormData()
    files.forEach(file => data.append('files', file))
    if (channelNames?.some(Boolean)) data.append('channel_names', JSON.stringify(channelNames))
    data.append('output_name', outputName); data.append('response_mode', 'resource')
    return fetch('/api/v1/convert/bmp-to-tiff', { method: 'POST', body: data }).then(parse<ImageResource>)
  },
  createAnnotation: (imageId: string) => {
    const data = new FormData(); data.append('image_id', imageId)
    return fetch('/api/v1/annotations', { method: 'POST', body: data }).then(parse<AnnotationResource>)
  },
  annotation: (id: string) => fetch(`/api/v1/annotations/${id}`).then(parse<AnnotationResource>),
  addClass: (id: string, value: Pick<AnnotationClass, 'name' | 'description' | 'color'>) => fetch(`/api/v1/annotations/${id}/classes`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) }).then(parse<AnnotationClass>),
  editClass: (annotationId: string, classId: number, value: Partial<AnnotationClass>) => fetch(`/api/v1/annotations/${annotationId}/classes/${classId}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) }).then(parse<AnnotationClass>),
  deleteClass: (annotationId: string, classId: number) => fetch(`/api/v1/annotations/${annotationId}/classes/${classId}`, { method: 'DELETE' }).then(parse<void>),
  reorderClasses: (id: string, classIds: number[]) => fetch(`/api/internal/v1/annotations/${id}/class-order`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ class_ids: classIds }) }).then(parse<{ classes: AnnotationClass[] }>),
  operation: (id: string, value: unknown) => fetch(`/api/internal/v1/annotations/${id}/operations`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) }).then(parse<Partial<AnnotationResource>>),
  history: (id: string, action: 'undo' | 'redo') => fetch(`/api/internal/v1/annotations/${id}/${action}`, { method: 'POST' }).then(parse<Partial<AnnotationResource>>),
  save: (id: string) => fetch(`/api/internal/v1/annotations/${id}/save`, { method: 'POST' }).then(parse<Partial<AnnotationResource>>),
  replaceMask: (id: string, files: File[], overwrite: boolean) => {
    const data = new FormData()
    const mask = files.find(file => /\.(tif|tiff|zip)$/i.test(file.name)); const metadata = files.find(file => /\.json$/i.test(file.name))
    if (mask) data.append('mask', mask); if (metadata) data.append('metadata', metadata)
    data.append('overwrite', String(overwrite))
    return fetch(`/api/v1/annotations/${id}/mask`, { method: 'PUT', body: data }).then(parse<AnnotationResource>)
  },
}
