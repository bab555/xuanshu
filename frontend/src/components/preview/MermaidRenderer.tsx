import React, { useEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';
import './MermaidRenderer.css';

interface MermaidRendererProps {
  code: string;
  onError?: (error: string) => void;
  onSuccess?: () => void;
}

// 初始化 Mermaid
mermaid.initialize({
  startOnLoad: false,
  theme: 'default',
  securityLevel: 'loose',
  fontFamily: 'sans-serif',
});

export const MermaidRenderer: React.FC<MermaidRendererProps> = ({
  code,
  onError,
  onSuccess,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const renderMermaid = async () => {
      if (!code.trim()) {
        setError('图表代码为空');
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        setError(null);

        const id = `mermaid-${Date.now()}-${Math.random().toString(36).slice(2)}`;
        const { svg: renderedSvg } = await mermaid.render(id, code.trim());
        
        setSvg(renderedSvg);
        setLoading(false);
        onSuccess?.();
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : '渲染失败';
        setError(errorMessage);
        setLoading(false);
        onError?.(errorMessage);
      }
    };

    renderMermaid();
  }, [code, onError, onSuccess]);

  if (loading) {
    return (
      <div className="mermaid-renderer mermaid-loading">
        <div className="mermaid-spinner" />
        <span>渲染中...</span>
      </div>
    );
  }

  if (error) {
    // 仅在控制台打印错误，UI 上显示一个温和的占位符或保留源代码
    console.warn('[Mermaid Render Error]', error);
    return (
      <div className="mermaid-renderer mermaid-error-silent">
        <div className="mermaid-source-preview">
            {/* 渲染失败时，直接展示代码块，避免大红报错影响体验 */}
            <pre>{code}</pre>
        </div>
        <div className="mermaid-error-hint" title={error}>
            ⚠️ 图表渲染异常，等待自动修复
        </div>
      </div>
    );
  }

  return (
    <div 
      className="mermaid-renderer mermaid-success"
      ref={containerRef}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
};

export default MermaidRenderer;
