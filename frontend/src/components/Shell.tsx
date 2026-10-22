import { BookOpen, Github, LogOut, UserRound } from 'lucide-react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useSession } from '../context/SessionContext'
import { useUnsaved } from '../context/UnsavedContext'

export function Shell() {
  const { dirty } = useUnsaved(); const { session } = useSession(); const navigate = useNavigate()
  const guarded = (event: React.MouseEvent<HTMLAnchorElement>, path: string) => {
    if (dirty && !window.confirm('You have unsaved annotation changes. Leave this page?')) event.preventDefault()
    else { event.preventDefault(); navigate(path) }
  }
  return <div className="app-shell">
    <header className="topbar">
      <Link className="brand" to="/" onClick={event => guarded(event, '/')}><span className="brand-mark">M</span>MulAn</Link>
      <nav aria-label="Main navigation">
        {[['/convert', 'Convert'], ['/viewer', 'Viewer'], ['/annotator', 'Annotator']].map(([to, label]) => <NavLink key={to} to={to} onClick={event => guarded(event, to)}>{label}</NavLink>)}
      </nav>
      <div className="user-menu"><span className="user-name" title={session.user?.email}><UserRound />{session.user?.display_name}</span><a className="sign-out" href={session.logout_url} onClick={event => { if (dirty && !window.confirm('You have unsaved annotation changes. Sign out anyway?')) event.preventDefault() }}><LogOut size={16} />Sign out</a></div>
    </header>
    <main><Outlet /></main>
    <footer><a href="/API.md"><BookOpen size={15} />Documentation</a><a href="https://github.com" target="_blank" rel="noreferrer"><Github size={15} />GitHub</a><span>MulAn v1</span></footer>
  </div>
}

