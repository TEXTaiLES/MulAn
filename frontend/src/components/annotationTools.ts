import { Brush, CircleOff, Hand, MousePointer2, Square } from 'lucide-react'

export type AnnotationTool = 'pan' | 'brush_add' | 'erase' | 'lasso_add' | 'lasso_subtract' | 'rectangle_add' | 'rectangle_subtract'

export const ANNOTATION_TOOLS = [
  { id: 'pan', label: 'Pan', shortcut: 'H', icon: Hand },
  { id: 'brush_add', label: 'Brush', shortcut: 'B', icon: Brush },
  { id: 'erase', label: 'Eraser', shortcut: 'E', icon: CircleOff },
  { id: 'lasso_add', label: 'Lasso Add', shortcut: 'L', icon: MousePointer2 },
  { id: 'lasso_subtract', label: 'Lasso Subtract', shortcut: 'Shift+L', icon: MousePointer2 },
  { id: 'rectangle_add', label: 'Rectangle Add', shortcut: 'R', icon: Square },
  { id: 'rectangle_subtract', label: 'Rectangle Subtract', shortcut: 'Shift+R', icon: Square },
] as const satisfies ReadonlyArray<{ id: AnnotationTool; label: string; shortcut: string; icon: typeof Brush }>

export type AnnotationHistoryAction = 'undo' | 'redo'

export const ANNOTATION_HISTORY_ACTIONS = [
  { id: 'undo', label: 'Undo', shortcut: 'Ctrl/Cmd+Z', ariaShortcut: 'Control+Z Meta+Z' },
  { id: 'redo', label: 'Redo', shortcut: 'Ctrl/Cmd+Shift+Z or Ctrl/Cmd+Y', ariaShortcut: 'Control+Shift+Z Meta+Shift+Z Control+Y Meta+Y' },
] as const satisfies ReadonlyArray<{ id: AnnotationHistoryAction; label: string; shortcut: string; ariaShortcut: string }>

function isEditableTarget(event: KeyboardEvent) {
  const target = event.target instanceof HTMLElement ? event.target : null
  return Boolean(target?.isContentEditable || target?.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"])'))
}

export function annotationToolForKey(event: KeyboardEvent): AnnotationTool | null {
  if (event.ctrlKey || event.altKey || event.metaKey || isEditableTarget(event)) return null
  const pressed = `${event.shiftKey ? 'Shift+' : ''}${event.key.toUpperCase()}`
  return ANNOTATION_TOOLS.find(item => item.shortcut === pressed)?.id ?? null
}

export function annotationHistoryActionForKey(event: KeyboardEvent): AnnotationHistoryAction | null {
  if (event.altKey || event.ctrlKey === event.metaKey || isEditableTarget(event)) return null
  const key = event.key.toUpperCase()
  if (key === 'Z') return event.shiftKey ? 'redo' : 'undo'
  return key === 'Y' && !event.shiftKey ? 'redo' : null
}
