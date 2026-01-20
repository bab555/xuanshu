import { useState, ReactNode } from 'react'
import './ThreeColumnLayout.css'

interface Props {
  left: ReactNode
  middle: ReactNode
  right: ReactNode
}

export function ThreeColumnLayout({ left, middle, right }: Props) {
  const [leftCollapsed, setLeftCollapsed] = useState(false)
  const [rightCollapsed, setRightCollapsed] = useState(false)

  return (
    <div className="three-column-layout">
      <aside className={`panel panel--left ${leftCollapsed ? 'collapsed' : ''}`}>
        <button
          className="collapse-btn collapse-btn--left"
          onClick={() => setLeftCollapsed(!leftCollapsed)}
          title={leftCollapsed ? '展开对话' : '收起对话'}
        >
          {leftCollapsed ? '→' : '←'}
        </button>
        {!leftCollapsed && <div className="panel-content">{left}</div>}
      </aside>

      <main className="panel panel--middle">
        <div className="panel-content">{middle}</div>
      </main>

      <aside className={`panel panel--right ${rightCollapsed ? 'collapsed' : ''}`}>
        <button
          className="collapse-btn collapse-btn--right"
          onClick={() => setRightCollapsed(!rightCollapsed)}
          title={rightCollapsed ? '展开预览' : '收起预览'}
        >
          {rightCollapsed ? '←' : '→'}
        </button>
        {!rightCollapsed && <div className="panel-content">{right}</div>}
      </aside>
    </div>
  )
}

