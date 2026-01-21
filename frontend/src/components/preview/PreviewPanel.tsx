import { useState } from 'react'
import { MarkdownRenderer } from './MarkdownRenderer'
import { ExportButton } from './ExportButton'
import './PreviewPanel.css'

interface Props {
  docId: string
  content: string
  onCodeBlockError?: (type: string, error: string, code: string) => void
}

export function PreviewPanel({ docId, content, onCodeBlockError }: Props) {
  const [activeTab, setActiveTab] = useState<'preview' | 'source'>('preview')

  const downloadMd = () => {
    const filename = `document_${docId}.md`
    const blob = new Blob([content || ''], { type: 'text/markdown;charset=utf-8' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
  }

  return (
    <div className="preview-panel">
      <div className="preview-header">
        <div className="preview-tabs">
          <button
            className={`preview-tab ${activeTab === 'preview' ? 'active' : ''}`}
            onClick={() => setActiveTab('preview')}
          >
            预览
          </button>
          <button
            className={`preview-tab ${activeTab === 'source' ? 'active' : ''}`}
            onClick={() => setActiveTab('source')}
          >
            源码
          </button>
        </div>
        <div className="preview-actions">
          <button
            className="export-button export-idle"
            onClick={downloadMd}
            disabled={!content}
            title="下载 Markdown"
          >
            <span className="export-icon">⬇</span>
            下载 MD
          </button>
          <ExportButton docId={docId} disabled={!content} />
        </div>
      </div>

      <div className="preview-content">
        {!content ? (
          <div className="preview-empty">
            <p>文档内容将在这里预览</p>
            <p className="preview-hint">支持 Markdown、Mermaid 图表、HTML 原型</p>
          </div>
        ) : activeTab === 'preview' ? (
          <div className="preview-markdown">
            <MarkdownRenderer 
              content={content} 
              onCodeBlockError={onCodeBlockError}
            />
          </div>
        ) : (
          <pre className="preview-source">{content}</pre>
        )}
      </div>
    </div>
  )
}

