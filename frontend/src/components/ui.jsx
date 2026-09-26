import { Link, NavLink } from 'react-router-dom'
import { CTA } from '../copy'

export function NavBar() {
  const item = ({ isActive }) =>
    `rounded-md px-3 py-1.5 text-sm transition ${isActive ? 'bg-slate-800 text-white' : 'text-slate-400 hover:text-white'}`
  return (
    <header className="sticky top-0 z-10 border-b border-slate-800/80 bg-slate-950/85 backdrop-blur">
      <nav className="mx-auto flex max-w-5xl items-center gap-2 px-4 py-3">
        <Link to="/" className="mr-auto flex items-center gap-2 font-semibold text-white">
          <span className="grid size-7 place-items-center rounded-md bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/30" aria-hidden>
            ◆
          </span>
          CodeSentinel
        </Link>
        <NavLink to="/run" className={item}>New Run</NavLink>
        <NavLink to="/history" className={item}>History</NavLink>
      </nav>
    </header>
  )
}

const BUTTON = {
  primary: 'bg-emerald-500 text-slate-950 hover:bg-emerald-400 disabled:bg-slate-700 disabled:text-slate-400',
  secondary: 'bg-slate-800 text-slate-100 ring-1 ring-slate-700 hover:bg-slate-700',
  ghost: 'text-slate-300 hover:text-white',
}

export function Button({ variant = 'primary', className = '', ...props }) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed ${BUTTON[variant]} ${className}`}
      {...props}
    />
  )
}

export function LinkButton({ variant = 'primary', className = '', ...props }) {
  return (
    <Link
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition ${BUTTON[variant]} ${className}`}
      {...props}
    />
  )
}

const BANNER = {
  error: 'border-rose-500/30 bg-rose-500/10 text-rose-200',
  success: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
  warning: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
  info: 'border-sky-500/30 bg-sky-500/10 text-sky-200',
}

export function Banner({ tone = 'info', children, action }) {
  return (
    <div role={tone === 'error' ? 'alert' : 'status'} className={`flex flex-wrap items-center gap-3 rounded-lg border px-4 py-3 text-sm ${BANNER[tone]}`}>
      <div className="flex-1">{children}</div>
      {action}
    </div>
  )
}

export function Spinner({ label }) {
  return (
    <div className="flex items-center gap-3 text-sm text-slate-400">
      <span className="size-4 animate-spin rounded-full border-2 border-slate-600 border-t-slate-200" />
      {label}
    </div>
  )
}

export function NotFound() {
  return (
    <div className="py-20 text-center">
      <h1 className="text-xl font-semibold text-white">Page not found</h1>
      <p className="mt-2 text-slate-400">That page doesn't exist.</p>
      <LinkButton to="/" variant="secondary" className="mt-6">Go to Home</LinkButton>
      <LinkButton to="/run" className="ml-3 mt-6">{CTA.startRun}</LinkButton>
    </div>
  )
}
