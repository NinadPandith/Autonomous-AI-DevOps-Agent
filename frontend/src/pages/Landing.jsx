import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { CTA } from '../copy'
import { LinkButton } from '../components/ui'

const STEPS = [
  {
    title: 'Detect',
    body: 'Runs the test suite and parses the failures to find where the code is likely broken.',
  },
  {
    title: 'Diagnose',
    body: 'Reads the code, works out the root cause, and explains its reasoning at every step.',
  },
  {
    title: 'Fix & Verify',
    body: 'Writes a patch and re-runs the full suite. If tests still fail, it reflects and tries again.',
  },
]

export default function Landing() {
  const [featured, setFeatured] = useState(null)

  useEffect(() => {
    api.featured()
      .then((runs) => setFeatured(runs.find((r) => r.status === 'fixed') ?? runs[0] ?? null))
      .catch(() => {})
  }, [])

  return (
    <div className="py-12 sm:py-20">
      <section className="max-w-2xl">
        <p className="text-sm font-medium text-emerald-300">Autonomous AI DevOps agent</p>
        <h1 className="mt-3 text-4xl font-semibold leading-tight tracking-tight text-white sm:text-5xl">
          An AI agent that finds, fixes, and verifies bugs — autonomously.
        </h1>
        <p className="mt-5 text-lg leading-relaxed text-slate-400">
          Point CodeSentinel at a repository. It detects failing tests, diagnoses the root cause, patches the code,
          and proves the fix by re-running the tests — with every step of its reasoning visible as it works.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-4">
          <LinkButton to="/run" className="px-5 py-2.5">{CTA.startRun}</LinkButton>
          {featured && (
            <LinkButton to={`/trace/${featured.id}?replay=1`} variant="secondary" className="px-5 py-2.5">
              ▶ {CTA.watchRecording}
            </LinkButton>
          )}
          <Link to="/history" className="text-sm font-medium text-slate-300 hover:text-white">
            {CTA.viewPastRuns} →
          </Link>
        </div>
      </section>

      <section className="mt-16 grid gap-4 sm:grid-cols-3" aria-label="How it works">
        {STEPS.map((step, i) => (
          <div key={step.title} className="rounded-xl border border-slate-800 bg-slate-900/50 p-5">
            <div className="flex items-center gap-3">
              <span className="grid size-7 place-items-center rounded-full bg-slate-800 font-mono text-xs text-slate-300">
                {i + 1}
              </span>
              <h2 className="font-semibold text-white">{step.title}</h2>
            </div>
            <p className="mt-3 text-sm leading-relaxed text-slate-400">{step.body}</p>
          </div>
        ))}
      </section>
    </div>
  )
}
