import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { CTA, ERRORS } from '../copy'
import { Banner, Button, LinkButton } from '../components/ui'

const GITHUB_URL = /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+?(\.git)?\/?$/
const DIFFICULTY_COLOR = { easy: 'text-emerald-300', medium: 'text-amber-300', hard: 'text-rose-300' }

function SourceOption({ checked, onChange, title, description, children }) {
  return (
    <label
      className={`block cursor-pointer rounded-xl border p-4 transition ${
        checked ? 'border-emerald-500/50 bg-emerald-500/5' : 'border-slate-800 bg-slate-900/40 hover:border-slate-700'
      }`}
    >
      <div className="flex items-start gap-3">
        <input type="radio" name="source" checked={checked} onChange={onChange} className="mt-1 accent-emerald-500" />
        <div className="flex-1">
          <div className="font-medium text-white">{title}</div>
          <p className="mt-0.5 text-sm text-slate-400">{description}</p>
          {checked && children}
        </div>
      </div>
    </label>
  )
}

export default function NewRun() {
  const navigate = useNavigate()
  const [source, setSource] = useState('demo')
  const [scenarios, setScenarios] = useState([])
  const [scenario, setScenario] = useState('B1')
  const [repoUrl, setRepoUrl] = useState('')
  const [urlError, setUrlError] = useState(null)
  const [error, setError] = useState(null)
  const [busyRunId, setBusyRunId] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const [userReposAllowed, setUserReposAllowed] = useState(null) // null = unknown yet
  const [trusted, setTrusted] = useState(false)

  useEffect(() => {
    api.scenarios().then(setScenarios).catch((err) => setError(err.message))
    api.health().then((h) => setUserReposAllowed(Boolean(h.allow_user_repos))).catch(() => {})
  }, [])

  const urlValid = GITHUB_URL.test(repoUrl.trim())
  const canSubmit = !submitting && (source === 'demo' || (urlValid && trusted && userReposAllowed))

  async function submit(event) {
    event.preventDefault()
    setError(null)
    setUrlError(null)
    setBusyRunId(null)
    setSubmitting(true)
    try {
      let repoId
      let bugIds
      if (source === 'demo') {
        repoId = (await api.demoRepo()).id
        bugIds = scenario === 'all' ? undefined : [scenario]
      } else {
        try {
          repoId = (await api.registerRepo(repoUrl.trim())).id
        } catch (err) {
          if (['INVALID_REPO_URL', 'REPO_NOT_ACCESSIBLE'].includes(err.code)) {
            setUrlError(ERRORS.invalidRepo)
            return
          }
          if (err.code === 'REPO_TOO_LARGE') {
            setUrlError(err.message)
            return
          }
          throw err
        }
      }
      const run = await api.startRun(repoId, bugIds)
      navigate(`/trace/${run.id}`)
    } catch (err) {
      if (err.code === 'AGENT_BUSY') setBusyRunId(err.message.match(/run_\w+/)?.[0] ?? null)
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-2xl py-10">
      <h1 className="text-2xl font-semibold text-white">New Run</h1>
      <p className="mt-1 text-slate-400">Choose what the agent should work on.</p>

      <div className="mt-8 space-y-3">
        <SourceOption
          checked={source === 'demo'}
          onChange={() => setSource('demo')}
          title={CTA.useDemo}
          description="A small Python shopping-cart library seeded with 8 realistic bugs and a 22-test suite."
        >
          <div className="mt-4">
            <label htmlFor="scenario" className="text-xs font-medium uppercase tracking-wide text-slate-400">
              Planted bugs to include
            </label>
            <select
              id="scenario"
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
              className="mt-1.5 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-emerald-500 focus:outline-none"
            >
              {scenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.id} · {s.title} ({s.difficulty})
                </option>
              ))}
              <option value="all">All 8 bugs at once (longest run)</option>
            </select>
            {scenario !== 'all' && scenarios.length > 0 && (
              <p className="mt-2 text-xs text-slate-500">
                Difficulty:{' '}
                <span className={DIFFICULTY_COLOR[scenarios.find((s) => s.id === scenario)?.difficulty]}>
                  {scenarios.find((s) => s.id === scenario)?.difficulty}
                </span>
                . A single bug is the quickest demo — usually under two minutes.
              </p>
            )}
          </div>
        </SourceOption>

        <SourceOption
          checked={source === 'url'}
          onChange={() => setSource('url')}
          title={CTA.pasteRepo}
          description="A public Python repository on GitHub with a pytest test suite. The agent clones it, installs its dependencies in an isolated environment, and runs its tests."
        >
          {userReposAllowed === false && (
            <p className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
              Running the agent on your own repositories is turned off on this server, because it executes that
              repository's code here. The server owner can enable it with <code className="font-mono">ALLOW_USER_REPOS=true</code>.
            </p>
          )}
          <input
            type="url"
            value={repoUrl}
            onChange={(e) => {
              setRepoUrl(e.target.value)
              setUrlError(null)
            }}
            placeholder="https://github.com/user/repo"
            aria-invalid={Boolean(urlError)}
            className="mt-3 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100 placeholder:text-slate-600 focus:border-emerald-500 focus:outline-none"
          />
          {repoUrl && !urlValid && !urlError && (
            <p className="mt-2 text-xs text-slate-500">Enter a URL like https://github.com/user/repo.</p>
          )}
          {urlError && <p className="mt-2 text-sm text-rose-300">{urlError}</p>}
          <label className="mt-4 flex items-start gap-2.5 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={trusted}
              onChange={(e) => setTrusted(e.target.checked)}
              disabled={userReposAllowed === false}
              className="mt-0.5 accent-emerald-500"
            />
            <span>
              I trust this repository's code. Its install scripts and tests will run on the machine hosting CodeSentinel.
            </span>
          </label>
        </SourceOption>
      </div>

      {error && (
        <div className="mt-6">
          <Banner
            tone="error"
            action={busyRunId && <LinkButton to={`/trace/${busyRunId}`} variant="secondary">Watch Current Run</LinkButton>}
          >
            {error}
          </Banner>
        </div>
      )}

      <div className="mt-8 flex items-center gap-4">
        <Button type="submit" disabled={!canSubmit} className="px-6 py-2.5">
          {submitting ? 'Starting…' : CTA.runAgent}
        </Button>
        <p className="text-xs text-slate-500">The agent works on an isolated copy — the original code is never modified.</p>
      </div>
    </form>
  )
}
