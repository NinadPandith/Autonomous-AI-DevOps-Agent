import { Component } from 'react'

// Catches render errors so one broken component shows a message instead of a blank page.
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { failed: false }
  }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error, info) {
    console.error('Page crashed', error, info.componentStack)
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div className="py-20 text-center">
        <h1 className="text-xl font-semibold text-white">Something went wrong on this page</h1>
        <p className="mt-2 text-slate-400">Reload the page, or go back to the start.</p>
        <div className="mt-6 flex justify-center gap-3">
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-semibold text-slate-100 ring-1 ring-slate-700 hover:bg-slate-700"
          >
            Reload
          </button>
          <a href="/" className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400">
            Go to Home
          </a>
        </div>
      </div>
    )
  }
}
