import { ChevronLeft, ChevronRight, Search, Tags } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiFailure } from '../api/client'
import { useSession } from '../context/SessionContext'
import type { ImagePage, ImageResource } from '../types'

const PER_PAGE = 12

/** Multispectral images stored in HESTIA, searchable by filename. */
export function ImageLibrary({ actionLabel, onOpen }: { actionLabel: string; onOpen: (image: ImageResource) => void }) {
  const { can } = useSession(); const [page, setPage] = useState(1); const [query, setQuery] = useState(''); const [search, setSearch] = useState(''); const [result, setResult] = useState<ImagePage | null>(null); const [error, setError] = useState(''); const readable = can('images_read')
  useEffect(() => {
    if (!readable) return
    let current = true; setError('')
    api.images({ page, per_page: PER_PAGE, q: search }).then(value => { if (current) setResult(value) }).catch(reason => { if (current) setError(reason instanceof ApiFailure ? reason.message : 'Could not load HESTIA images.') })
    return () => { current = false }
  }, [readable, page, search])
  if (!readable) return <p className="notice" role="status">Your HESTIA account does not have access to multispectral images.</p>
  const pages = result ? Math.max(1, Math.ceil(result.total / result.per_page)) : 1
  const submit = (event: FormEvent) => { event.preventDefault(); setPage(1); setSearch(query.trim()) }
  return <section className="image-library" aria-label="HESTIA images">
    <div className="library-heading"><div><span className="eyebrow">HESTIA</span><h2>Multispectral images</h2></div><form className="library-search" role="search" onSubmit={submit}><input aria-label="Search images by filename" placeholder="Search by filename" value={query} onChange={event => setQuery(event.target.value)} /><button type="submit" aria-label="Search"><Search /></button></form></div>
    {error && <p className="error" role="alert">{error}</p>}
    {!result && !error && <p className="loading">Loading HESTIA images…</p>}
    {result && result.items.length === 0 && <p className="library-empty">{search ? `No images match “${search}”.` : 'There are no multispectral images in HESTIA yet.'}</p>}
    {result && result.items.length > 0 && <ul className="library-list">{result.items.map(image => <li key={image.image_id}>
      <div className="library-item"><strong>{image.filename}</strong><small>{image.width} × {image.height} · {image.channel_count} channels · {image.dtype}{image.created_by?.display_name ? ` · ${image.created_by.display_name}` : ''}{image.created_at ? ` · ${new Date(image.created_at).toLocaleDateString()}` : ''}</small></div>
      {image.has_annotation && <span className="annotated-badge" title="This image has a saved annotation"><Tags size={14} />Annotated</span>}
      <button className="secondary" aria-label={`${actionLabel} ${image.filename}`} onClick={() => onOpen(image)}>{actionLabel}</button>
    </li>)}</ul>}
    {result && pages > 1 && <div className="library-pages"><button aria-label="Previous page" disabled={page <= 1} onClick={() => setPage(value => value - 1)}><ChevronLeft /></button><span>Page {page} of {pages}</span><button aria-label="Next page" disabled={page >= pages} onClick={() => setPage(value => value + 1)}><ChevronRight /></button></div>}
  </section>
}
