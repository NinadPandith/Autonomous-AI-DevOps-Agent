import { useState } from 'react'
import { STEP_TYPES, TOOL_LABELS } from '../copy'

const ACCENT = {
  plan: 'border-l-sky-400',
  tool_call: 'border-l-amber-400',
  result: 'border-l-slate-500',
  reflection: 'border-l-violet-400',
}

const LABEL_COLOR = {
  plan: 'text-sky-300',
  tool_call: 'text-amber-300',
  result: 'text-slate-400',
  reflection: 'text-violet-300',
}

// Pick the most useful raw detail to show when a step is expanded.
function detailFor(step) {
  const out = step.tool_output
  const inp = step.tool_input
  if (step.step_type === 'result' && out) {
    if (typeof out.output === 'string') return out.output
    if (typeof out.content === 'string') return out.content
    if (Array.isArray(out.matches)) return out.matches.join('\n') || 'No matches.'
    if (Array.isArray(out.files)) return out.files.join('\n')
    if (out.error) return out.error
    return JSON.stringify(out, null, 2)
  }
  if (step.step_type === 'tool_call' && inp && Object.keys(inp).length) {
    if (step.tool_name === 'edit_file') {
      return `--- replace in ${inp.path}\n${inp.old_str}\n+++ with\n${inp.new_str}`
    }
    return JSON.stringify(inp, null, 2)
  }
  return null
}

export default function ReasoningStepCard({ step, animate = false }) {
  const [open, setOpen] = useState(false)
  const meta = STEP_TYPES[step.step_type] ?? { label: step.step_type, icon: '•' }
  const detail = detailFor(step)
  const tool = step.tool_name ? TOOL_LABELS[step.tool_name] ?? step.tool_name : null
  const emphasized = step.step_type === 'plan' || step.step_type === 'reflection'

  return (
    <article className={`${animate ? 'animate-step-in ' : ''}rounded-lg border border-slate-800 border-l-4 ${ACCENT[step.step_type] ?? ''} bg-slate-900/60 px-4 py-3`}>
      <header className="flex items-center gap-2 text-xs">
        <span aria-hidden>{meta.icon}</span>
        <span className={`font-semibold uppercase tracking-wide ${LABEL_COLOR[step.step_type] ?? ''}`}>{meta.label}</span>
        {tool && <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[11px] text-slate-300">{tool}</span>}
        <span className="ml-auto font-mono text-slate-600">#{step.sequence}</span>
      </header>
      <p className={`mt-1.5 whitespace-pre-wrap leading-relaxed ${emphasized ? 'text-slate-100' : 'text-slate-300'} text-sm`}>
        {step.content}
      </p>
      {detail && (
        <div className="mt-2">
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            className="text-xs text-slate-400 underline-offset-2 hover:text-slate-200 hover:underline"
            aria-expanded={open}
          >
            {open ? 'Hide details' : 'Show details'}
          </button>
          {open && (
            <pre className="mt-2 max-h-80 overflow-auto rounded-md bg-slate-950 p-3 font-mono text-xs leading-relaxed text-slate-300">
              {detail}
            </pre>
          )}
        </div>
      )}
    </article>
  )
}
