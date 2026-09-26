import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { NavBar, NotFound } from './components/ui'
import FixReview from './pages/FixReview'
import History from './pages/History'
import Landing from './pages/Landing'
import LiveTrace from './pages/LiveTrace'
import NewRun from './pages/NewRun'

export default function App() {
  return (
    <BrowserRouter>
      <NavBar />
      <main className="mx-auto max-w-5xl px-4">
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/run" element={<NewRun />} />
          <Route path="/trace/:runId" element={<LiveTrace />} />
          <Route path="/review/:runId" element={<FixReview />} />
          <Route path="/history" element={<History />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}
