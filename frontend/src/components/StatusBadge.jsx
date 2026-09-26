import { STATUS } from '../copy'

const TONES = {
  blue: 'bg-sky-500/10 text-sky-300 ring-sky-500/30',
  green: 'bg-emerald-500/10 text-emerald-300 ring-emerald-500/30',
  red: 'bg-rose-500/10 text-rose-300 ring-rose-500/30',
  amber: 'bg-amber-500/10 text-amber-300 ring-amber-500/30',
}

export default function StatusBadge({ status }) {
  const { label, tone } = STATUS[status] ?? { label: 'Unknown', tone: 'blue' }
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${TONES[tone]}`}>
      {status === 'running' && <span className="size-1.5 animate-pulse rounded-full bg-sky-400" />}
      {label}
    </span>
  )
}
