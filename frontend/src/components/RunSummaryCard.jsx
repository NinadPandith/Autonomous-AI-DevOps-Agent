import { Link } from 'react-router-dom'
import { repoName } from '../copy'
import { formatDateTime, formatDuration } from '../format'
import StatusBadge from './StatusBadge'

// Compact summary of a run. `variant="row"` renders a clickable History row;
// the default renders the header card used on the Review page.
export default function RunSummaryCard({ run, variant = 'card' }) {
  const to = run.status === 'running' ? `/trace/${run.id}` : `/review/${run.id}`
  const facts = [
    ['Started', formatDateTime(run.started_at)],
    ['Duration', run.status === 'running' ? 'In progress' : formatDuration(run.started_at, run.completed_at)],
    ['Attempts', run.attempt_count],
  ]

  if (variant === 'row') {
    return (
      <Link
        to={to}
        className="grid grid-cols-2 items-center gap-x-4 gap-y-1 px-4 py-3 text-sm transition hover:bg-slate-900 sm:grid-cols-[1.4fr_1fr_1.3fr_0.8fr_0.6fr]"
      >
        <span className="truncate font-medium text-slate-100">{repoName(run.repo_url)}</span>
        <span><StatusBadge status={run.status} /></span>
        <span className="text-slate-400">{formatDateTime(run.started_at)}</span>
        <span className="text-slate-400">{facts[1][1]}</span>
        <span className="text-slate-400">{run.attempt_count} {run.attempt_count === 1 ? 'attempt' : 'attempts'}</span>
        {run.diagnosis_summary && (
          <span className="col-span-full truncate text-xs text-slate-500">{run.diagnosis_summary}</span>
        )}
      </Link>
    )
  }

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-semibold text-white">{repoName(run.repo_url)}</h1>
        <StatusBadge status={run.status} />
        <span className="font-mono text-xs text-slate-500">{run.id}</span>
      </div>
      <dl className="mt-4 grid grid-cols-3 gap-4 text-sm">
        {facts.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs uppercase tracking-wide text-slate-500">{label}</dt>
            <dd className="mt-0.5 text-slate-200">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
