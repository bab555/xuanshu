import React, { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { MermaidRenderer } from './MermaidRenderer';
import { HtmlSandbox } from './HtmlSandbox';
import './MarkdownRenderer.css';

interface MarkdownRendererProps {
  content: string;
  onCodeBlockError?: (type: string, error: string) => void;
}

export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({
  content,
  onCodeBlockError,
}) => {
  // 自定义代码块渲染
  const components = useMemo(() => ({
    code: ({ className, children, ...props }: any) => {
      const match = /language-(\w+)/.exec(className || '');
      const language = match ? match[1] : '';
      const codeContent = String(children).replace(/\n$/, '');

      // Mermaid 代码块
      if (language === 'mermaid') {
        return (
          <MermaidRenderer 
            code={codeContent}
            onError={(err) => onCodeBlockError?.('mermaid', err)}
          />
        );
      }

      // HTML 代码块
      if (language === 'html') {
        return (
          <HtmlSandbox 
            code={codeContent}
            onError={(err) => onCodeBlockError?.('html', err)}
          />
        );
      }

      // 其他代码块
      return (
        <pre className={`code-block ${language ? `language-${language}` : ''}`}>
          <code {...props}>{children}</code>
        </pre>
      );
    },
    // 表格样式
    table: ({ children }: any) => (
      <div className="table-wrapper">
        <table>{children}</table>
      </div>
    ),
    // 链接新窗口打开
    a: ({ href, children }: any) => (
      <a href={href} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    ),
  }), [onCodeBlockError]);

  if (!content) {
    return (
      <div className="markdown-renderer markdown-empty">
        <div className="empty-icon">📄</div>
        <p>暂无内容</p>
      </div>
    );
  }

  return (
    <div className="markdown-renderer">
      <ReactMarkdown 
        remarkPlugins={[remarkGfm]}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
};

export default MarkdownRenderer;
