import { useEffect, useRef } from 'react'
import { useParams } from 'react-router-dom'
import ReasoningStepCard from '../components/ReasoningStepCard'
import StatusBadge from '../components/StatusBadge'
import { Banner, LinkButton, NotFound, Spinner } from '../components/ui'
import useRunStream from '../hooks/useRunStream'
import { CTA, ERRORS, repoName } from '../copy'

function Progress({ run }) {
  const max = run.max_attempts ?? 3
  const current = Math.min(run.attempt_count ?? 0, max)
  return (
    <div className="flex items-center gap-3" aria-label={`Attempt ${current} of ${max}`}>
      <div className="flex gap-1">
        {Array.from({ length: max }, (_, i) => (
          <span
            key={i}
            className={`h-1.5 w-8 rounded-full ${
              i < current ? (run.status === 'running' && i === current - 1 ? 'animate-pulse bg-sky-400' : 'bg-slate-400') : 'bg-slate-800'
            }`}
          />
        ))}
      </div>
      <span className="text-sm text-slate-400">{current === 0 ? 'Investigating' : `Attempt ${current} of ${max}`}</span>
    </div>
  )
}

function FinishedBanner({ run, streamError }) {
  const review = <LinkButton to={`/review/${run.id}`}>{CTA.viewFix}</LinkButton>
  if (run.status === 'fixed') {
    return <Banner tone="success" action={review}>Fix verified ✅ — every test passes after the agent's changes.</Banner>
  }
  if (run.status === 'needs_review') {
    return (
      <Banner tone="warning" action={review}>
        The agent made progress but recommends a manual review before trusting this fix.
      </Banner>
    )
  }
  const timedOut = (streamError ?? run.diagnosis_summary ?? '').includes('took too long')
  return (
    <Banner tone="error" action={review}>
      {timedOut ? ERRORS.timeout : streamError ?? ERRORS.exhausted(run.attempt_count || run.max_attempts || 3)}
    </Banner>
  )
}

export default function LiveTraceRoute() {
  const { runId } = useParams()
  return <LiveTrace key={runId} runId={runId} />
}

function LiveTrace({ runId }) {
  const { run, steps, hydratedCount, error, streamError, connection } = useRunStream(runId)
  const bottomRef = useRef(null)
  const followRef = useRef(true)
  const running = run?.status === 'running'

  // Keep the newest step in view, unless the user has scrolled up to read.
  useEffect(() => {
    const onScroll = () => {
      followRef.current = window.innerHeight + window.scrollY >= document.body.scrollHeight - 120
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])
  useEffect(() => {
    if (steps.length > hydratedCount && followRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [steps.length, hydratedCount])

  // Warn before leaving mid-run (App Flow §2.3).
  useEffect(() => {
    if (!running) return
    const warn = (e) => e.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [running])

  if (error?.code === 'RUN_NOT_FOUND') return <NotFound />
  if (error) return <div className="py-10"><Banner tone="error">{error.message}</Banner></div>
  if (!run) return <div className="py-10"><Spinner label="Loading run…" /></div>

  return (
    <div className="py-8">
      <header className="sticky top-[57px] z-[5] -mx-4 border-b border-slate-800/60 bg-slate-950/90 px-4 pb-4 pt-2 backdrop-blur">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold text-white">{repoName(run.repo_url)}</h1>
          <StatusBadge status={run.status} />
          <span className="ml-auto text-xs text-slate-500">
            {connection === 'live' && '● Live'}
            {connection === 'polling' && 'Reconnecting — updating every few seconds'}
          </span>
        </div>
        <div className="mt-3"><Progress run={run} /></div>
      </header>

      <div className="mt-6 space-y-3">
        {steps.map((step, i) => (
          <ReasoningStepCard key={step.sequence} step={step} animate={i >= hydratedCount} />
        ))}
        {running && (
          <div className="rounded-lg border border-dashed border-slate-800 px-4 py-3">
            <Spinner label="The agent is working…" />
          </div>
        )}
      </div>

      {!running && (
        <div className="mt-6"><FinishedBanner run={run} streamError={streamError} /></div>
      )}
      <div ref={bottomRef} className="h-4" />
    </div>
  )
}
