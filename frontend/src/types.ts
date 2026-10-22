export interface ImageResource {
  image_id: string
  filename: string
  width: number
  height: number
  channel_count: number
  dtype: string
  channel_names: (string | null)[]
  georeferenced: boolean
  download_url?: string
  has_annotation?: boolean
  annotation_updated_at?: string | null
  created_at?: string
  created_by?: { id: string; display_name: string | null } | null
  size_bytes?: number
}

export interface ImagePage {
  items: ImageResource[]
  page: number
  per_page: number
  total: number
}

export type Capability = 'images_read' | 'images_create' | 'annotations_read' | 'annotations_create' | 'annotations_update'

export interface HestiaSession {
  authenticated: boolean
  user: { id: string; email: string; display_name: string } | null
  capabilities: Record<Capability, boolean>
  login_url: string
  logout_url: string
}

export interface AnnotationClass {
  id: number
  name: string
  description: string
  color: string
  order?: number
  visible?: boolean
}

export interface AnnotationResource {
  annotation_id: string
  image_id: string
  filename: string
  width: number
  height: number
  channel_count: number
  revision: number
  saved_revision: number
  classes: AnnotationClass[]
  can_undo: boolean
  can_redo: boolean
  /** HESTIA revision this working copy was opened from or last saved as; null until first saved. */
  hestia_revision: number | null
  statistics?: { class_id: number; pixel_count: number }[]
}

