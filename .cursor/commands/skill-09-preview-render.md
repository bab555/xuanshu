# skill-09：预览渲染（Mermaid/HTML/Markdown）

> 对应开发文档：§3.2 预览渲染、§11 前端组件结构

## 目标

实现右侧 PreviewPanel 的渲染：
- Markdown 渲染
- Mermaid 图表渲染（带错误定位）
- HTML 原型受控渲染
- 预览必须"做好"，尽可能接近最终导出效果

## 组件实现

### components/preview/PreviewPanel.tsx

```tsx
import { useState } from 'react';
import { MarkdownRenderer } from './MarkdownRenderer';
import { ExportButton } from './ExportButton';
import './PreviewPanel.css';

interface Props {
  docId: string;
  content: string;  // final_md 或 draft_md
  version?: string;
}

export function PreviewPanel({ docId, content, version }: Props) {
  const [activeTab, setActiveTab] = useState<'preview' | 'source'>('preview');

  return (
    <div className="preview-panel">
      <div className="preview-header">
        <div className="preview-tabs">
          <button
            className={activeTab === 'preview' ? 'active' : ''}
            onClick={() => setActiveTab('preview')}
          >
            预览
          </button>
          <button
            className={activeTab === 'source' ? 'active' : ''}
            onClick={() => setActiveTab('source')}
          >
            源码
          </button>
        </div>
        <ExportButton docId={docId} />
      </div>
      
      <div className="preview-content">
        {activeTab === 'preview' ? (
          <MarkdownRenderer content={content} />
        ) : (
          <pre className="source-view">{content}</pre>
        )}
      </div>
    </div>
  );
}
```

### components/preview/MarkdownRenderer.tsx

```tsx
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { MermaidRenderer } from './MermaidRenderer';
import { HtmlSandbox } from './HtmlSandbox';

interface Props {
  content: string;
}

export function MarkdownRenderer({ content }: Props) {
  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ node, inline, className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '');
            const lang = match?.[1];
            
            if (!inline && lang === 'mermaid') {
              return <MermaidRenderer code={String(children).trim()} />;
            }
            
            // 检查是否是 PROTO_HTML 块（通过父级注释识别）
            // 实际实现需要在预处理阶段提取
            
            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
        }}
      >
        {preprocessContent(content)}
      </ReactMarkdown>
    </div>
  );
}

function preprocessContent(content: string): string {
  // 预处理：提取 PROTO_HTML 块并转换为可渲染格式
  // 把 <!--PROTO_HTML:id=xxx-->...<!--/PROTO_HTML--> 转换为特殊标记
  return content.replace(
    /<!--PROTO_HTML:id=([^>]+)-->([\s\S]*?)<!--\/PROTO_HTML-->/g,
    (_, id, html) => `\n\n<div data-proto-html="${id}">${html}</div>\n\n`
  );
}
```

### components/preview/MermaidRenderer.tsx

```tsx
import { useEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';

interface Props {
  code: string;
  id?: string;
}

// 初始化 Mermaid
mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  securityLevel: 'loose',
});

export function MermaidRenderer({ code, id }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [svg, setSvg] = useState<string>('');

  useEffect(() => {
    const render = async () => {
      try {
        setError(null);
        const uniqueId = `mermaid-${id || Date.now()}`;
        const { svg } = await mermaid.render(uniqueId, code);
        setSvg(svg);
      } catch (err: any) {
        setError(err.message || '渲染失败');
        console.error('Mermaid render error:', err);
      }
    };
    
    render();
  }, [code, id]);

  if (error) {
    return (
      <div className="mermaid-error">
        <div className="error-header">
          <span className="error-icon">⚠️</span>
          <span>Mermaid 渲染失败</span>
        </div>
        <pre className="error-message">{error}</pre>
        <details>
          <summary>源代码</summary>
          <pre className="error-source">{code}</pre>
        </details>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="mermaid-container"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
```

### components/preview/HtmlSandbox.tsx

```tsx
import { useEffect, useRef } from 'react';

interface Props {
  html: string;
  id?: string;
}

// 允许的标签白名单
const ALLOWED_TAGS = new Set([
  'div', 'span', 'p', 'h1', 'h2', 'h3', 'h4',
  'ul', 'ol', 'li', 'table', 'tr', 'td', 'th', 'thead', 'tbody',
  'pre', 'code', 'strong', 'em', 'br', 'hr',
]);

// 允许的样式属性白名单
const ALLOWED_STYLES = new Set([
  'color', 'background-color', 'background', 'border', 'border-radius',
  'padding', 'margin', 'font-size', 'font-weight', 'text-align',
  'display', 'flex', 'flex-direction', 'justify-content', 'align-items',
  'grid', 'gap', 'width', 'height', 'max-width', 'min-width',
]);

export function HtmlSandbox({ html, id }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    
    // 创建 shadow DOM 隔离样式
    const shadow = containerRef.current.attachShadow?.({ mode: 'closed' })
      || containerRef.current;
    
    // 基础样式
    const style = document.createElement('style');
    style.textContent = `
      :host {
        display: block;
        padding: 16px;
        background: var(--bg-surface, #242424);
        border: 1px solid var(--border-color, #3A3A3A);
        border-radius: 8px;
        font-family: var(--font-family, sans-serif);
        color: var(--text-primary, #F5F5F5);
      }
      * { box-sizing: border-box; }
    `;
    
    // 清理 HTML（移除危险内容）
    const sanitized = sanitizeHtml(html);
    
    shadow.innerHTML = '';
    shadow.appendChild(style);
    
    const content = document.createElement('div');
    content.innerHTML = sanitized;
    shadow.appendChild(content);
    
  }, [html]);

  return (
    <div
      ref={containerRef}
      className="html-sandbox"
      data-proto-id={id}
    />
  );
}

function sanitizeHtml(html: string): string {
  // 简单的 HTML 清理（生产环境应使用 DOMPurify）
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, 'text/html');
  
  // 移除脚本和危险标签
  doc.querySelectorAll('script, link, iframe, object, embed').forEach(el => el.remove());
  
  // 移除事件处理器
  doc.querySelectorAll('*').forEach(el => {
    Array.from(el.attributes).forEach(attr => {
      if (attr.name.startsWith('on')) {
        el.removeAttribute(attr.name);
      }
    });
  });
  
  return doc.body.innerHTML;
}
```

### 样式文件

```css
/* preview/PreviewPanel.css */
.preview-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-base);
}

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid var(--border-color);
}

.preview-tabs {
  display: flex;
  gap: var(--spacing-xs);
}

.preview-tabs button {
  padding: 6px 12px;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 4px;
}

.preview-tabs button.active {
  background: var(--bg-elevated);
  color: var(--text-primary);
}

.preview-content {
  flex: 1;
  overflow: auto;
  padding: var(--spacing-md);
}

.markdown-body {
  color: var(--text-primary);
  line-height: 1.6;
}

.markdown-body h1, .markdown-body h2, .markdown-body h3 {
  margin-top: 1.5em;
  margin-bottom: 0.5em;
}

.markdown-body code {
  background: var(--bg-elevated);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: var(--font-mono);
}

.markdown-body pre {
  background: var(--bg-elevated);
  padding: var(--spacing-md);
  border-radius: var(--border-radius);
  overflow-x: auto;
}

.mermaid-container {
  margin: var(--spacing-md) 0;
  padding: var(--spacing-md);
  background: var(--bg-surface);
  border-radius: var(--border-radius);
  text-align: center;
}

.mermaid-error {
  background: rgba(244, 67, 54, 0.1);
  border: 1px solid var(--color-error);
  border-radius: var(--border-radius);
  padding: var(--spacing-md);
  margin: var(--spacing-md) 0;
}

.mermaid-error .error-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  color: var(--color-error);
  font-weight: 600;
  margin-bottom: var(--spacing-sm);
}

.mermaid-error pre {
  background: var(--bg-elevated);
  padding: var(--spacing-sm);
  border-radius: 4px;
  font-size: var(--font-size-sm);
  overflow-x: auto;
}
```

## 验收标准

- [ ] Markdown 正确渲染（标题/列表/表格/代码块）
- [ ] Mermaid 图表正确渲染
- [ ] Mermaid 渲染失败时显示错误信息和源码
- [ ] HTML 原型在受控容器中渲染，不污染全局样式
- [ ] 大文档不卡顿（可考虑懒加载）
- [ ] 预览效果接近最终导出效果

