import { useEffect, useState } from 'react'
import { api } from '../api'
import RunSummaryCard from '../components/RunSummaryCard'
import { Banner, LinkButton, Spinner } from '../components/ui'
import { CTA, STATUS } from '../copy'

const FILTERS = [
  ['all', 'All'],
  ['fixed', STATUS.fixed.label],
  ['failed', STATUS.failed.label],
  ['needs_review', STATUS.needs_review.label],
]

export default function History() {
  const [filter, setFilter] = useState('all')
  const [runs, setRuns] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    api.runs(filter === 'all' ? undefined : filter)
      .then((r) => !cancelled && setRuns(r))
      .catch((err) => !cancelled && setError(err.message))
    return () => { cancelled = true }
  }, [filter])

  return (
    <div className="py-10">
      <div className="flex flex-wrap items-end gap-4">
        <div className="mr-auto">
          <h1 className="text-2xl font-semibold text-white">Past Runs</h1>
          <p className="mt-1 text-slate-400">Every run the agent has made, newest first.</p>
        </div>
        <div className="inline-flex rounded-lg bg-slate-900 p-1 text-sm ring-1 ring-slate-800" role="tablist">
          {FILTERS.map(([value, label]) => (
            <button
              key={value}
              role="tab"
              aria-selected={filter === value}
              onClick={() => {
                if (value === filter) return
                setRuns(null)
                setError(null)
                setFilter(value)
              }}
              className={`rounded-md px-3 py-1.5 ${filter === value ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-6">
        {error && <Banner tone="error">{error}</Banner>}
        {!error && !runs && <Spinner label="Loading runs…" />}
        {runs && runs.length === 0 && (
          <div className="rounded-xl border border-dashed border-slate-800 py-14 text-center">
            <p className="text-slate-400">{filter === 'all' ? 'No runs yet.' : 'No runs with this status yet.'}</p>
            <LinkButton to="/run" className="mt-4">{CTA.startRun}</LinkButton>
          </div>
        )}
        {runs && runs.length > 0 && (
          <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/40">
            <div className="hidden grid-cols-[1.4fr_1fr_1.3fr_0.8fr_0.6fr] gap-x-4 border-b border-slate-800 px-4 py-2 text-xs font-medium uppercase tracking-wide text-slate-500 sm:grid">
              <span>Repository</span><span>Status</span><span>Started</span><span>Time taken</span><span>Attempts</span>
            </div>
            <div className="divide-y divide-slate-800">
              {runs.map((run) => <RunSummaryCard key={run.id} run={run} variant="row" />)}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
