import React, { useRef, useEffect, useState } from 'react';
import './HtmlSandbox.css';

interface HtmlSandboxProps {
  code: string;
  width?: number;
  onError?: (error: string) => void;
  onSuccess?: () => void;
}

export const HtmlSandbox: React.FC<HtmlSandboxProps> = ({
  code,
  width = 800,
  onError,
  onSuccess,
}) => {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [height, setHeight] = useState(200);

  useEffect(() => {
    if (!code.trim()) {
      setError('HTML 代码为空');
      return;
    }

    const iframe = iframeRef.current;
    if (!iframe) return;

    try {
      setError(null);

      // 构造完整的 HTML 文档
      const fullHtml = `
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            * { box-sizing: border-box; }
            body { 
              margin: 0; 
              padding: 10px; 
              font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
              background: white;
            }
          </style>
        </head>
        <body>
          ${code}
          <script>
            // 通知父窗口内容高度
            window.addEventListener('load', function() {
              const height = document.body.scrollHeight;
              window.parent.postMessage({ type: 'resize', height: height }, '*');
            });
          </script>
        </body>
        </html>
      `;

      // 使用 srcdoc 设置内容
      iframe.srcdoc = fullHtml;

      // 监听高度变化
      const handleMessage = (event: MessageEvent) => {
        if (event.data?.type === 'resize') {
          setHeight(Math.min(event.data.height + 20, 600));
        }
      };

      window.addEventListener('message', handleMessage);
      onSuccess?.();

      return () => {
        window.removeEventListener('message', handleMessage);
      };
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '渲染失败';
      setError(errorMessage);
      onError?.(errorMessage);
    }
  }, [code, onError, onSuccess]);

  if (error) {
    return (
      <div className="html-sandbox html-error">
        <div className="error-icon">⚠️</div>
        <div className="error-message">
          <strong>HTML 渲染失败</strong>
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
    <div className="html-sandbox" style={{ maxWidth: width }}>
      <div className="sandbox-header">
        <span className="sandbox-label">HTML 原型预览</span>
        <span className="sandbox-size">{width}px</span>
      </div>
      <iframe
        ref={iframeRef}
        className="sandbox-frame"
        style={{ height }}
        sandbox="allow-scripts"
        title="HTML Preview"
      />
    </div>
  );
};

export default HtmlSandbox;

