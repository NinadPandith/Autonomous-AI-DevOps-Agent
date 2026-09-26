import { BrowserRouter, Route, Routes, useLocation } from 'react-router-dom'
import ErrorBoundary from './components/ErrorBoundary'
import { NavBar, NotFound } from './components/ui'
import FixReview from './pages/FixReview'
import History from './pages/History'
import Landing from './pages/Landing'
import LiveTrace from './pages/LiveTrace'
import NewRun from './pages/NewRun'

// Reset the error boundary whenever the route changes, so one crashed page doesn't stick.
function Pages() {
  const location = useLocation()
  return (
    <ErrorBoundary key={location.pathname}>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/run" element={<NewRun />} />
        <Route path="/trace/:runId" element={<LiveTrace />} />
        <Route path="/review/:runId" element={<FixReview />} />
        <Route path="/history" element={<History />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </ErrorBoundary>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <NavBar />
      <main className="mx-auto max-w-5xl px-4">
        <Pages />
      </main>
    </BrowserRouter>
  )
}
