// What this file does: Root router — gates all pages behind login, renders the Layout shell.
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext.jsx'
import Login from './pages/Login.jsx'
import Layout from './components/Layout.jsx'
import Dashboard from './pages/Dashboard.jsx'
import MarketData from './pages/MarketData.jsx'
import Predictor from './pages/Predictor.jsx'
import SectorView from './pages/SectorView.jsx'
import Comparison from './pages/Comparison.jsx'

function PrivateRoute({ children }) {
  const { user } = useAuth()
  return user ? children : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <div className="scanlines">
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={
            <PrivateRoute>
              <Layout />
            </PrivateRoute>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard"   element={<Dashboard />} />
          <Route path="market"      element={<MarketData />} />
          <Route path="predictor"   element={<Predictor />} />
          <Route path="sectors"     element={<SectorView />} />
          <Route path="comparison"  element={<Comparison />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  )
}
