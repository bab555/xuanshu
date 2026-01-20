import { Link, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth'
import './Header.css'

export function Header() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <header className="header">
      <div className="header-left">
        <Link to="/my" className="header-logo">
          📄 红点集团内部文档工具
        </Link>
      </div>

      <nav className="header-nav">
        <Link
          to="/my"
          className={`header-nav-item ${location.pathname === '/my' ? 'active' : ''}`}
        >
          我的文档
        </Link>
        <Link
          to="/shared"
          className={`header-nav-item ${location.pathname === '/shared' ? 'active' : ''}`}
        >
          抄送给我
        </Link>
      </nav>

      <div className="header-right">
        {user && (
          <>
            <span className="header-username">{user.username}</span>
            <button className="btn btn-secondary header-logout" onClick={handleLogout}>
              退出
            </button>
          </>
        )}
      </div>
    </header>
  )
}

