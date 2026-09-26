import { useEffect, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import ReasoningStepCard from '../components/ReasoningStepCard'
import StatusBadge from '../components/StatusBadge'
import { Banner, Button, LinkButton, NotFound, Spinner } from '../components/ui'
import useRunStream from '../hooks/useRunStream'
import { CTA, ERRORS, repoName } from '../copy'

// Replay speed: real gaps between steps are compressed, then clamped to keep it watchable.
const REPLAY_SPEEDUP = 0.15
const REPLAY_MIN_MS = 250
const REPLAY_MAX_MS = 1600

function replayDelay(steps, i) {
  if (i === 0) return REPLAY_MIN_MS
  const gap = new Date(steps[i].created_at) - new Date(steps[i - 1].created_at)
  return Math.min(REPLAY_MAX_MS, Math.max(REPLAY_MIN_MS, gap * REPLAY_SPEEDUP))
}

function Progress({ current, max, active }) {
  return (
    <div className="flex items-center gap-3" aria-label={`Attempt ${current} of ${max}`}>
      <div className="flex gap-1">
        {Array.from({ length: max }, (_, i) => (
          <span
            key={i}
            className={`h-1.5 w-8 rounded-full ${
              i < current ? (active && i === current - 1 ? 'animate-pulse bg-sky-400' : 'bg-slate-400') : 'bg-slate-800'
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
  if (run.status === 'needs_review' && !run.attempt_count && run.diagnosis_summary) {
    // Stopped before attempting a fix (setup problem, no tests, nothing failing): say why.
    return <Banner tone="warning" action={review}>{run.diagnosis_summary}</Banner>
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
  const [searchParams] = useSearchParams()
  // null = show everything; a number = replaying a finished run, showing that many steps so far.
  const [replayShown, setReplayShown] = useState(() => (searchParams.get('replay') === '1' ? 0 : null))
  const bottomRef = useRef(null)
  const followRef = useRef(true)
  const running = run?.status === 'running'
  const replaying = !running && run != null && replayShown !== null && replayShown < steps.length
  const visible = replaying ? steps.slice(0, replayShown) : steps

  // Advance the replay one step at a time.
  useEffect(() => {
    if (!replaying) return
    const timer = setTimeout(() => setReplayShown((n) => n + 1), replayDelay(steps, replayShown))
    return () => clearTimeout(timer)
  }, [replaying, replayShown, steps])

  // Keep the newest step in view, unless the user has scrolled up to read.
  useEffect(() => {
    const onScroll = () => {
      followRef.current = window.innerHeight + window.scrollY >= document.body.scrollHeight - 120
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])
  useEffect(() => {
    if ((replaying || visible.length > hydratedCount) && followRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [visible.length, hydratedCount, replaying])

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

  const maxAttempts = run.max_attempts ?? 3
  // During a replay, the attempt counter follows the steps shown so far.
  const investigating = !visible.some((s) => s.tool_name === 'parse_failures' && s.step_type === 'result')
  const replayAttempt = investigating ? 0
    : Math.min(visible.filter((s) => s.tool_name === 'submit_fix').length + 1, run.attempt_count || 1)
  const attempt = replaying ? replayAttempt : Math.min(run.attempt_count ?? 0, maxAttempts)

  return (
    <div className="py-8">
      <header className="sticky top-[57px] z-[5] -mx-4 border-b border-slate-800/60 bg-slate-950/90 px-4 pb-4 pt-2 backdrop-blur">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold text-white">{repoName(run.repo_url)}</h1>
          <StatusBadge status={replaying ? 'running' : run.status} />
          {replaying && (
            <span className="rounded-full bg-violet-500/10 px-2.5 py-0.5 text-xs font-medium text-violet-300 ring-1 ring-inset ring-violet-500/30">
              Replay · sped up
            </span>
          )}
          <span className="ml-auto flex items-center gap-3 text-xs text-slate-500">
            {connection === 'live' && '● Live'}
            {connection === 'polling' && 'Reconnecting — updating every few seconds'}
            {!running && !replaying && steps.length > 0 && (
              <Button variant="ghost" className="px-2 py-1 text-xs" onClick={() => setReplayShown(0)}>
                ▶ Replay this run
              </Button>
            )}
            {replaying && (
              <Button variant="ghost" className="px-2 py-1 text-xs" onClick={() => setReplayShown(steps.length)}>
                Skip to end
              </Button>
            )}
          </span>
        </div>
        <div className="mt-3"><Progress current={attempt} max={maxAttempts} active={running || replaying} /></div>
      </header>

      {replaying && replayShown === 0 && (
        <div className="mt-6">
          <Banner tone="info">
            This is a recording of a real run, replayed faster than it happened. Start a new run to watch the agent live.
          </Banner>
        </div>
      )}

      <div className="mt-6 space-y-3">
        {visible.map((step, i) => (
          <ReasoningStepCard key={step.sequence} step={step} animate={replaying || i >= hydratedCount} />
        ))}
        {(running || replaying) && (
          <div className="rounded-lg border border-dashed border-slate-800 px-4 py-3">
            <Spinner label="The agent is working…" />
          </div>
        )}
      </div>

      {!running && !replaying && (
        <div className="mt-6"><FinishedBanner run={run} streamError={streamError} /></div>
      )}
      <div ref={bottomRef} className="h-4" />
    </div>
  )
}
