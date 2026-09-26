export function formatDateTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export function formatDuration(startIso, endIso) {
  if (!startIso || !endIso) return '—'
  const seconds = Math.max(0, Math.round((new Date(endIso) - new Date(startIso)) / 1000))
  if (seconds < 60) return `${seconds}s`
  return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, '0')}s`
}

// "22 passed in 0.04s" / "2 failed, 20 passed in 0.1s" -> { passed, failed, total }
export function parseTestSummary(summary) {
  const count = (word) => Number(summary?.match(new RegExp(`(\\d+) ${word}`))?.[1] ?? 0)
  const passed = count('passed')
  const failed = count('failed') + count('errors?')
  return { passed, failed, total: passed + failed }
}

// Backend diffs concatenate files as "# ===== path =====\n<content>". Split them back out.
export function splitFiles(concatenated) {
  const files = {}
  const parts = (concatenated ?? '').split(/^# ===== (.+?) =====\n/m)
  for (let i = 1; i < parts.length; i += 2) files[parts[i]] = parts[i + 1] ?? ''
  return files
}
