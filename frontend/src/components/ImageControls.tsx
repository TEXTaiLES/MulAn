import { ChevronLeft, ChevronRight, Maximize, Minus, Plus } from 'lucide-react'

export function ImageControls({ channel, count, onChannel, onZoom, onFit }: { channel: number; count: number; onChannel: (value: number) => void; onZoom: (factor: number) => void; onFit: () => void }) {
  return <div className="image-controls" aria-label="Image controls">
    <button aria-label="Previous channel" title="Previous channel" disabled={channel === 0} onClick={() => onChannel(channel - 1)}><ChevronLeft />Previous</button>
    <strong>Channel {channel + 1} / {count}</strong>
    <button aria-label="Next channel" title="Next channel" disabled={channel === count - 1} onClick={() => onChannel(channel + 1)}>Next<ChevronRight /></button>
    <span className="control-divider" />
    <button aria-label="Zoom out" title="Zoom out" onClick={() => onZoom(0.8)}><Minus /></button>
    <button aria-label="Zoom in" title="Zoom in" onClick={() => onZoom(1.25)}><Plus /></button>
    <button aria-label="Fit to viewport" title="Fit to viewport" onClick={onFit}><Maximize /></button>
  </div>
}

