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
  statistics?: { class_id: number; pixel_count: number }[]
}

