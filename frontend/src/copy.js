// All user-facing copy that follows a wording rule lives here,
// so the five pages stay consistent. Never show raw internal values — map them through these tables.

export const STATUS = {
  running: { label: 'Running', tone: 'blue' },
  fixed: { label: 'Fixed & Verified', tone: 'green' },
  failed: { label: 'Could Not Fix', tone: 'red' },
  needs_review: { label: 'Needs Review', tone: 'amber' },
}

export const STEP_TYPES = {
  plan: { label: 'Plan', icon: '🧠' },
  tool_call: { label: 'Tool Call', icon: '🔧' },
  result: { label: 'Result', icon: '📄' },
  reflection: { label: 'Reflection', icon: '🔁' },
}

export const TOOL_LABELS = {
  run_tests: 'Run Tests',
  parse_failures: 'Parse Failures',
  list_files: 'List Files',
  read_file: 'Read Code',
  search_code: 'Search Code',
  edit_file: 'Generate Patch',
  submit_fix: 'Submit Fix',
  revert: 'Revert Attempt',
  llm: 'Model',
  clone_repo: 'Clone Repo',
  install_deps: 'Install Dependencies',
}

export const CTA = {
  startRun: 'Start a New Run',
  viewPastRuns: 'View Past Runs',
  useDemo: 'Use Demo Repository',
  pasteRepo: 'Paste Your Own Repo',
  runAgent: 'Run Agent',
  viewFix: 'View Fix',
  runAgain: 'Run Again',
  viewAllRuns: 'View All Runs',
  viewTrace: 'View Trace',
  downloadPatch: 'Download Patch',
  watchRecording: 'Watch a Recorded Run',
}

export const ERRORS = {
  invalidRepo: "That repository couldn't be accessed. Make sure the URL is correct and the repo is public.",
  backendUnreachable: "Couldn't reach the agent right now. Please try again in a moment.",
  exhausted: (n) => `The agent attempted ${n} fix${n === 1 ? '' : 'es'} but couldn't resolve this issue. See its findings below.`,
  timeout: 'This run took too long and was stopped for safety. Try a smaller repository or a simpler bug.',
  runNotFound: "This run doesn't exist. It may have been removed, or the link is incorrect.",
}

export function confidenceMessage(score) {
  if (score == null) return null
  if (score >= 0.8) return 'The agent is confident this fix resolves the issue.'
  if (score >= 0.5) return 'The agent believes this fix likely resolves the issue, but recommends a manual review.'
  return "The agent's fix did not fully resolve the issue — manual investigation is recommended."
}

export function repoName(url) {
  if (!url) return 'Repository'
  if (url.startsWith('local://')) return url.slice('local://'.length)
  return url.replace(/^https:\/\/github\.com\//, '')
}
