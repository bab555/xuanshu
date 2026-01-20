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
    return (
      <div className="mermaid-renderer mermaid-error">
        <div className="error-icon">⚠️</div>
        <div className="error-message">
          <strong>图表渲染失败</strong>
          <pre>{error}</pre>
        </div>
        <details className="error-code">
          <summary>查看源代码</summary>
          <pre>{code}</pre>
        </details>
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
