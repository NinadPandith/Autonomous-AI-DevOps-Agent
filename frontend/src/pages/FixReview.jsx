import { createTwoFilesPatch } from 'diff'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'
import DiffViewer from '../components/DiffViewer'
import RunSummaryCard from '../components/RunSummaryCard'
import { Banner, Button, LinkButton, NotFound, Spinner } from '../components/ui'
import { CTA, ERRORS, confidenceMessage } from '../copy'
import { parseTestSummary, splitFiles } from '../format'

function downloadPatch(runId, fix) {
  const before = splitFiles(fix.diff_before)
  const after = splitFiles(fix.diff_after)
  const patch = Object.keys(after)
    .map((path) => createTwoFilesPatch(`a/${path}`, `b/${path}`, before[path] ?? '', after[path]))
    .join('\n')
  const url = URL.createObjectURL(new Blob([patch], { type: 'text/x-diff' }))
  const link = Object.assign(document.createElement('a'), { href: url, download: `${runId}.patch` })
  link.click()
  URL.revokeObjectURL(url)
}

function Verification({ fix }) {
  const { passed, failed, total } = parseTestSummary(fix.tests_summary)
  if (fix.tests_passed) {
    return (
      <p className="flex items-center gap-2 text-emerald-300">
        <span aria-hidden>✅</span> All {total || passed} tests passing after fix
      </p>
    )
  }
  return (
    <p className="flex items-center gap-2 text-rose-300">
      <span aria-hidden>❌</span> Fix did not resolve failing tests
      {total > 0 && <span className="text-slate-400">({failed} of {total} still failing)</span>}
    </p>
  )
}

export default function FixReviewRoute() {
  const { runId } = useParams()
  return <FixReview key={runId} runId={runId} />
}

function FixReview({ runId }) {
  const [run, setRun] = useState(null)
  const [fix, setFix] = useState(undefined) // undefined = loading, null = no fix produced
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    api.run(runId)
      .then((r) => !cancelled && setRun(r))
      .catch((err) => !cancelled && setError(err))
    api.fix(runId)
      .then((f) => !cancelled && setFix(f))
      .catch((err) => {
        if (cancelled) return
        if (err.code === 'NO_FIX_YET') setFix(null)
        else setError(err)
      })
    return () => { cancelled = true }
  }, [runId])

  if (error?.code === 'RUN_NOT_FOUND') return <NotFound />
  if (error) return <div className="py-10"><Banner tone="error">{error.message}</Banner></div>
  if (!run || fix === undefined) return <div className="py-10"><Spinner label="Loading results…" /></div>

  const confidence = confidenceMessage(run.final_confidence_score)
  const unresolved = run.status === 'failed'

  return (
    <div className="space-y-6 py-8">
      <RunSummaryCard run={run} />

      {run.status === 'running' && (
        <Banner tone="info" action={<LinkButton to={`/trace/${run.id}`} variant="secondary">{CTA.viewTrace}</LinkButton>}>
          This run is still in progress. The results below may change.
        </Banner>
      )}
      {unresolved && (
        <Banner tone="error">
          {(run.diagnosis_summary ?? '').includes('took too long') ? ERRORS.timeout : ERRORS.exhausted(run.attempt_count || 3)}
        </Banner>
      )}

      <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Diagnosis</h2>
        <p className="mt-2 text-lg leading-relaxed text-slate-100">
          {run.diagnosis_summary ?? 'The agent did not reach a diagnosis for this run.'}
        </p>
        <div className="mt-4 space-y-1.5 text-sm">
          {fix && <Verification fix={fix} />}
          {confidence && (
            <p className="text-slate-300">
              {confidence}{' '}
              <span className="text-slate-500">(confidence {Math.round(run.final_confidence_score * 100)}%)</span>
            </p>
          )}
        </div>
      </section>

      <section>
        <div className="mb-3 flex flex-wrap items-baseline gap-2">
          <h2 className="text-lg font-semibold text-white">Changes</h2>
          {fix && (
            <span className="text-sm text-slate-500">
              {fix.tests_passed ? 'Verified' : 'Best'} attempt {fix.attempt_number} of {fix.total_attempts}
              {' · '}{fix.files_changed.length} file{fix.files_changed.length === 1 ? '' : 's'} changed
            </span>
          )}
        </div>
        {fix ? (
          <DiffViewer before={fix.diff_before} after={fix.diff_after} />
        ) : (
          <p className="rounded-xl border border-slate-800 p-5 text-sm text-slate-400">
            The agent did not produce a patch in this run. Its reasoning is still available in the trace.
          </p>
        )}
      </section>

      <div className="flex flex-wrap gap-3 border-t border-slate-800 pt-6">
        {fix && fix.files_changed.length > 0 && (
          <Button variant="secondary" onClick={() => downloadPatch(run.id, fix)}>{CTA.downloadPatch}</Button>
        )}
        <LinkButton to={`/trace/${run.id}`} variant="secondary">{CTA.viewTrace}</LinkButton>
        <LinkButton to="/run">{CTA.runAgain}</LinkButton>
        <LinkButton to="/history" variant="ghost">{CTA.viewAllRuns} →</LinkButton>
      </div>
    </div>
  )
}
