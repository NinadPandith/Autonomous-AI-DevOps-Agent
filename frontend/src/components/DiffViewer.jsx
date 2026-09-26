import { useState } from 'react'
import ReactDiffViewer, { DiffMethod } from 'react-diff-viewer-continued'
import { splitFiles } from '../format'

const DIFF_STYLES = {
  variables: {
    dark: {
      diffViewerBackground: '#0b1120',
      gutterBackground: '#0f172a',
      addedBackground: 'rgba(16, 185, 129, 0.12)',
      addedGutterBackground: 'rgba(16, 185, 129, 0.2)',
      removedBackground: 'rgba(244, 63, 94, 0.12)',
      removedGutterBackground: 'rgba(244, 63, 94, 0.2)',
      wordAddedBackground: 'rgba(16, 185, 129, 0.35)',
      wordRemovedBackground: 'rgba(244, 63, 94, 0.35)',
      codeFoldBackground: '#111827',
      codeFoldGutterBackground: '#111827',
      emptyLineBackground: '#0b1120',
    },
  },
  contentText: { fontFamily: 'var(--font-mono)', fontSize: '12.5px', fontVariantLigatures: 'none' },
}

// Renders one before/after diff per changed file. `before`/`after` are the backend's
// concatenated file blobs ("# ===== path =====" headers).
export default function DiffViewer({ before, after }) {
  const [split, setSplit] = useState(true)
  const beforeFiles = splitFiles(before)
  const afterFiles = splitFiles(after)
  const paths = [...new Set([...Object.keys(beforeFiles), ...Object.keys(afterFiles)])]

  if (!paths.length) {
    return <p className="text-sm text-slate-400">No code changes were recorded for this run.</p>
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <div className="inline-flex rounded-md bg-slate-900 p-0.5 text-xs ring-1 ring-slate-800">
          {[
            ['Side by side', true],
            ['Unified', false],
          ].map(([label, value]) => (
            <button
              key={label}
              type="button"
              onClick={() => setSplit(value)}
              className={`rounded px-2.5 py-1 ${split === value ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      {paths.map((path) => (
        <section key={path} className="overflow-hidden rounded-lg ring-1 ring-slate-800">
          <h3 className="border-b border-slate-800 bg-slate-900 px-4 py-2 font-mono text-sm text-slate-200">{path}</h3>
          <div className="overflow-x-auto">
            <ReactDiffViewer
              oldValue={beforeFiles[path] ?? ''}
              newValue={afterFiles[path] ?? ''}
              splitView={split}
              useDarkTheme
              compareMethod={DiffMethod.WORDS}
              extraLinesSurroundingDiff={4}
              leftTitle={split ? 'Before' : undefined}
              rightTitle={split ? 'After' : undefined}
              styles={DIFF_STYLES}
            />
          </div>
        </section>
      ))}
    </div>
  )
}
