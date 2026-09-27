// Thin client for the CodeSentinel backend: REST API + WebSocket stream.
import { ERRORS } from './copy'

export const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8010/api'
export const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8010/ws'

export class ApiError extends Error {
  constructor(code, message, status) {
    super(message)
    this.code = code
    this.status = status
  }
}

async function request(path, options = {}) {
  let res
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...options.headers },
    })
  } catch (err) {
    console.error('Network error', path, err)
    throw new ApiError('NETWORK', ERRORS.backendUnreachable, 0)
  }
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    const error = body?.error ?? {}
    console.error('API error', res.status, path, body)
    throw new ApiError(error.code ?? 'UNKNOWN', error.message ?? ERRORS.backendUnreachable, res.status)
  }
  return body
}

export const api = {
  health: () => request('/health'),
  demoRepo: () => request('/repos/demo'),
  scenarios: () => request('/repos/demo/scenarios').then((r) => r.scenarios),
  registerRepo: (repoUrl) => request('/repos', { method: 'POST', body: JSON.stringify({ repo_url: repoUrl }) }),
  startRun: (repoId, bugIds) =>
    request('/runs', { method: 'POST', body: JSON.stringify({ repo_id: repoId, ...(bugIds ? { bug_ids: bugIds } : {}) }) }),
  run: (id) => request(`/runs/${id}`),
  reasoning: (id) => request(`/runs/${id}/reasoning`).then((r) => r.steps),
  fix: (id) => request(`/runs/${id}/fix`),
  runs: (status) => request(`/runs${status ? `?status=${status}` : ''}`).then((r) => r.runs),
  featured: () => request('/runs/featured').then((r) => r.runs),
}

export function runSocketUrl(runId) {
  return `${WS_URL}/runs/${runId}`
}
