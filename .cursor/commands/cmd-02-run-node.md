# skill-02：前端骨架（React + 三栏布局 + 样式系统）

> 对应开发文档：§3 前端设计、§11 前端组件结构与样式约定

## 目标

搭建前端项目骨架，包含：
- Vite + React + TypeScript 项目
- 三栏布局组件
- CSS 变量系统（深色主题）
- 基础组件库
- API 请求封装

## 目录结构

```
frontend/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Header.tsx
│   │   │   ├── ThreeColumnLayout.tsx
│   │   │   └── Sidebar.tsx
│   │   ├── chat/
│   │   │   ├── ChatPanel.tsx
│   │   │   ├── MessageList.tsx
│   │   │   ├── MessageItem.tsx
│   │   │   ├── ChatInput.tsx
│   │   │   └── AttachmentPreview.tsx
│   │   ├── flow/
│   │   │   ├── FlowPanel.tsx
│   │   │   ├── NodeCard.tsx
│   │   │   ├── NodePromptSpec.tsx
│   │   │   ├── NodeOutput.tsx
│   │   │   └── NodeTimeline.tsx
│   │   ├── preview/
│   │   │   ├── PreviewPanel.tsx
│   │   │   ├── MarkdownRenderer.tsx
│   │   │   ├── MermaidRenderer.tsx
│   │   │   ├── HtmlSandbox.tsx
│   │   │   └── ExportButton.tsx
│   │   └── common/
│   │       ├── Button.tsx
│   │       ├── Card.tsx
│   │       ├── Modal.tsx
│   │       ├── VirtualList.tsx
│   │       └── JsonEditor.tsx
│   ├── pages/
│   │   ├── Login.tsx
│   │   ├── Register.tsx
│   │   ├── MyDocs.tsx
│   │   ├── SharedDocs.tsx
│   │   └── DocEditor.tsx
│   ├── hooks/
│   │   ├── useWebSocket.ts
│   │   ├── useDocVariables.ts
│   │   └── useFlowRun.ts
│   ├── services/
│   │   └── api.ts
│   ├── types/
│   │   └── index.ts
│   └── styles/
│       ├── variables.css
│       ├── global.css
│       └── components/
└── public/
```

## 关键文件实现

### variables.css（样式系统核心）

```css
:root {
  /* 主色调 - 红点品牌色 */
  --color-primary: #E53935;
  --color-primary-hover: #C62828;
  
  /* 背景层次（深色主题） */
  --bg-base: #1A1A1A;
  --bg-surface: #242424;
  --bg-elevated: #2E2E2E;
  
  /* 文字 */
  --text-primary: #F5F5F5;
  --text-secondary: #A0A0A0;
  --text-muted: #6B6B6B;
  
  /* 状态色 */
  --color-success: #4CAF50;
  --color-warning: #FF9800;
  --color-error: #F44336;
  --color-info: #2196F3;
  --color-pending: #9E9E9E;
  --color-running: #2196F3;
  
  /* 边框与圆角 */
  --border-color: #3A3A3A;
  --border-radius: 8px;
  
  /* 间距 */
  --spacing-xs: 4px;
  --spacing-sm: 8px;
  --spacing-md: 16px;
  --spacing-lg: 24px;
  --spacing-xl: 32px;
  
  /* 字体 */
  --font-family: 'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
  --font-size-sm: 13px;
  --font-size-base: 14px;
  --font-size-lg: 16px;
  --font-size-xl: 20px;
  
  /* 布局尺寸 */
  --chat-panel-width: 320px;
  --preview-panel-width: 480px;
  --header-height: 56px;
}
```

### ThreeColumnLayout.tsx

```tsx
import { useState, ReactNode } from 'react';
import './ThreeColumnLayout.css';

interface Props {
  left: ReactNode;
  middle: ReactNode;
  right: ReactNode;
}

export function ThreeColumnLayout({ left, middle, right }: Props) {
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);

  return (
    <div className="three-column-layout">
      <aside className={`panel panel--left ${leftCollapsed ? 'collapsed' : ''}`}>
        <button className="collapse-btn" onClick={() => setLeftCollapsed(!leftCollapsed)}>
          {leftCollapsed ? '→' : '←'}
        </button>
        {!leftCollapsed && left}
      </aside>
      
      <main className="panel panel--middle">
        {middle}
      </main>
      
      <aside className={`panel panel--right ${rightCollapsed ? 'collapsed' : ''}`}>
        <button className="collapse-btn" onClick={() => setRightCollapsed(!rightCollapsed)}>
          {rightCollapsed ? '←' : '→'}
        </button>
        {!rightCollapsed && right}
      </aside>
    </div>
  );
}
```

### ThreeColumnLayout.css

```css
.three-column-layout {
  display: flex;
  height: calc(100vh - var(--header-height));
  background: var(--bg-base);
}

.panel {
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border-color);
  position: relative;
}

.panel--left {
  width: var(--chat-panel-width);
  min-width: 280px;
  max-width: 400px;
  resize: horizontal;
  overflow: auto;
}

.panel--left.collapsed {
  width: 40px;
  min-width: 40px;
}

.panel--middle {
  flex: 1;
  min-width: 400px;
  overflow: auto;
}

.panel--right {
  width: var(--preview-panel-width);
  min-width: 360px;
  max-width: 600px;
  resize: horizontal;
  overflow: auto;
  border-right: none;
  border-left: 1px solid var(--border-color);
}

.panel--right.collapsed {
  width: 40px;
  min-width: 40px;
}

.collapse-btn {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  background: var(--bg-elevated);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  cursor: pointer;
  padding: 8px 4px;
  border-radius: 4px;
  z-index: 10;
}

.panel--left .collapse-btn { right: -12px; }
.panel--right .collapse-btn { left: -12px; }
```

### NodeCard.tsx（中间栏核心组件）

```tsx
import { NodeRun } from '@/types';
import { NodePromptSpec } from './NodePromptSpec';
import { NodeOutput } from './NodeOutput';
import './NodeCard.css';

interface Props {
  node: NodeRun;
  onRerun?: () => void;
}

const NODE_LABELS: Record<string, string> = {
  controller: 'A：中控对话',
  writer: 'B：文档撰写',
  diagram: 'C：图文助手',
  image: 'D：生图助手',
  assembler: 'E：全文整合',
  attachment: 'F：附件分析',
  export: 'X：导出',
};

export function NodeCard({ node, onRerun }: Props) {
  return (
    <div className={`node-card node-card--${node.status}`}>
      <div className="node-card__header">
        <span className="node-card__type">{NODE_LABELS[node.node_type]}</span>
        <span className={`node-card__status status--${node.status}`}>
          {node.status}
        </span>
      </div>
      
      <NodePromptSpec spec={node.prompt_spec} />
      
      {node.result && <NodeOutput result={node.result} />}
      
      {node.error && (
        <div className="node-card__error">
          <strong>{node.error.error_type}</strong>
          <p>{node.error.error_message}</p>
          <code>{node.error.retry_guidance}</code>
        </div>
      )}
      
      <div className="node-card__actions">
        {node.status === 'fail' && onRerun && (
          <button onClick={onRerun}>重跑此节点</button>
        )}
      </div>
    </div>
  );
}
```

### api.ts（请求封装）

```typescript
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = localStorage.getItem('token');
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export const api = {
  auth: {
    login: (data: { username: string; password: string }) =>
      request('/auth/login', { method: 'POST', body: JSON.stringify(data) }),
    register: (data: { username: string; password: string }) =>
      request('/auth/register', { method: 'POST', body: JSON.stringify(data) }),
  },
  docs: {
    my: () => request('/docs/my'),
    cc: () => request('/docs/cc'),
    create: () => request('/docs', { method: 'POST' }),
    get: (id: string) => request(`/docs/${id}`),
    share: (id: string, to: string) =>
      request(`/docs/${id}/share`, { method: 'POST', body: JSON.stringify({ to_username: to }) }),
  },
  workflow: {
    run: (docId: string, data: { user_message?: string; from_node?: string }) =>
      request(`/docs/${docId}/workflow/run`, { method: 'POST', body: JSON.stringify(data) }),
    status: (runId: string) => request(`/workflow/runs/${runId}`),
  },
  attachments: {
    upload: async (docId: string, file: File) => {
      const form = new FormData();
      form.append('file', file);
      form.append('doc_id', docId);
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_BASE}/attachments`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });
      return res.json();
    },
  },
  exports: {
    create: (docId: string) =>
      request(`/docs/${docId}/export/docx`, { method: 'POST' }),
    status: (exportId: string) => request(`/exports/${exportId}`),
  },
};
```

## package.json 依赖

```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.20.0",
    "mermaid": "^10.6.0",
    "react-markdown": "^9.0.0",
    "remark-gfm": "^4.0.0",
    "@tanstack/react-virtual": "^3.0.0"
  },
  "devDependencies": {
    "@types/react": "^18.2.0",
    "@vitejs/plugin-react": "^4.2.0",
    "typescript": "^5.3.0",
    "vite": "^5.0.0"
  }
}
```

## 验收标准

- [ ] `npm run dev` 能启动
- [ ] 三栏布局显示正确，可折叠
- [ ] 深色主题样式生效
- [ ] 节点卡片能渲染不同状态（pending/running/success/fail）
