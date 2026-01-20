import { Routes, Route, Navigate } from 'react-router-dom'
import { Login } from './pages/Login'
import { Register } from './pages/Register'
import { MyDocs } from './pages/MyDocs'
import { SharedDocs } from './pages/SharedDocs'
import { DocEditor } from './pages/DocEditor'
import { useAuthStore } from './stores/auth'

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  if (!token) {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        path="/my"
        element={
          <PrivateRoute>
            <MyDocs />
          </PrivateRoute>
        }
      />
      <Route
        path="/shared"
        element={
          <PrivateRoute>
            <SharedDocs />
          </PrivateRoute>
        }
      />
      <Route
        path="/doc/:docId"
        element={
          <PrivateRoute>
            <DocEditor />
          </PrivateRoute>
        }
      />
      <Route path="/" element={<Navigate to="/my" replace />} />
    </Routes>
  )
}

