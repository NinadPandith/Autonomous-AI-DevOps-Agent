import { useEffect, useRef, useState } from 'react'
import { api, runSocketUrl } from '../api'

const POLL_MS = 3000

function mergeSteps(existing, incoming) {
  const bySeq = new Map(existing.map((s) => [s.sequence, s]))
  for (const s of incoming) bySeq.set(s.sequence, s)
  return [...bySeq.values()].sort((a, b) => a.sequence - b.sequence)
}

// Live view of one run: hydrates from REST, then follows the WebSocket.
// If the socket drops while the run is still going, it falls back to polling.
// Mount with key={runId} so state starts fresh for each run.
export default function useRunStream(runId) {
  const [run, setRun] = useState(null)
  const [steps, setSteps] = useState([])
  const [hydratedCount, setHydratedCount] = useState(0) // steps already recorded when the page loaded
  const [error, setError] = useState(null) // ApiError from loading
  const [streamError, setStreamError] = useState(null) // agent-reported error message
  const [connection, setConnection] = useState('connecting') // connecting | live | polling | closed
  const runRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    let socket = null
    let pollTimer = null

    const updateRun = (patch) =>
      setRun((prev) => {
        const next = { ...(prev ?? {}), ...patch }
        runRef.current = next
        return next
      })

    const poll = async () => {
      try {
        const [r, s] = await Promise.all([api.run(runId), api.reasoning(runId)])
        if (cancelled) return
        updateRun(r)
        setSteps((prev) => mergeSteps(prev, s))
        if (r.status === 'running') pollTimer = setTimeout(poll, POLL_MS)
        else setConnection('closed')
      } catch {
        if (!cancelled) pollTimer = setTimeout(poll, POLL_MS * 2)
      }
    }

    const openSocket = () => {
      socket = new WebSocket(runSocketUrl(runId))
      socket.onopen = () => !cancelled && setConnection('live')
      socket.onmessage = (event) => {
        const msg = JSON.parse(event.data)
        if (msg.type === 'reasoning_step') setSteps((prev) => mergeSteps(prev, [msg.data]))
        else if (msg.type === 'status_update') updateRun(msg.data)
        else if (msg.type === 'error') setStreamError(msg.data.message)
      }
      socket.onclose = () => {
        if (cancelled) return
        if (runRef.current?.status === 'running') {
          setConnection('polling')
          poll()
        } else {
          setConnection('closed')
          // Pick up final fields (diagnosis, confidence) the socket doesn't carry.
          api.run(runId).then((r) => !cancelled && updateRun(r)).catch(() => {})
        }
      }
    }

    ;(async () => {
      try {
        const [r, s] = await Promise.all([api.run(runId), api.reasoning(runId)])
        if (cancelled) return
        updateRun(r)
        setSteps(s)
        setHydratedCount(s.length)
        if (r.status === 'running') openSocket()
        else setConnection('closed')
      } catch (err) {
        if (!cancelled) setError(err)
      }
    })()

    return () => {
      cancelled = true
      clearTimeout(pollTimer)
      if (socket) {
        socket.onclose = null
        socket.close()
      }
    }
  }, [runId])

  return { run, steps, hydratedCount, error, streamError, connection }
}
