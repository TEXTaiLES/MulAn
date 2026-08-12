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

export function annotationToolForKey(event: KeyboardEvent): AnnotationTool | null {
  if (event.ctrlKey || event.altKey || event.metaKey) return null
  const target = event.target instanceof HTMLElement ? event.target : null
  if (target?.isContentEditable || target?.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"])')) return null
  const pressed = `${event.shiftKey ? 'Shift+' : ''}${event.key.toUpperCase()}`
  return ANNOTATION_TOOLS.find(item => item.shortcut === pressed)?.id ?? null
}
