import React, { useState } from 'react';
import { api } from '../../services/api';
import './ExportButton.css';

interface ExportButtonProps {
  docId: string;
  disabled?: boolean;
}

type ExportStatus = 'idle' | 'exporting' | 'success' | 'error';

export const ExportButton: React.FC<ExportButtonProps> = ({ 
  docId, 
  disabled = false 
}) => {
  const [status, setStatus] = useState<ExportStatus>('idle');
  const [error, setError] = useState<string | null>(null);

  const handleExport = async () => {
    if (disabled || status === 'exporting') return;

    try {
      setStatus('exporting');
      setError(null);

      // 调用导出 API
      const response = await api.post(`/export/${docId}`, {}, {
        responseType: 'blob',
        timeout: 120000, // 导出可能较慢，2分钟超时
      });

      // 从响应头获取文件名
      const contentDisposition = response.headers['content-disposition'];
      let filename = `document_${docId}.docx`;
      if (contentDisposition) {
        const match = contentDisposition.match(/filename="?(.+)"?/);
        if (match) {
          filename = decodeURIComponent(match[1]);
        }
      }

      // 创建下载链接
      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
      });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);

      setStatus('success');
      
      // 3秒后重置状态
      setTimeout(() => {
        setStatus('idle');
      }, 3000);

    } catch (err: any) {
      console.error('Export error:', err);
      
      let errorMessage = '导出失败';
      if (err.response?.status === 404) {
        errorMessage = '文档不存在';
      } else if (err.response?.status === 400) {
        errorMessage = '文档内容为空';
      } else if (err.code === 'ECONNABORTED') {
        errorMessage = '导出超时，请稍后重试';
      } else if (err.response?.data) {
        // 尝试解析错误信息
        try {
          const text = await err.response.data.text();
          const json = JSON.parse(text);
          errorMessage = json.detail || errorMessage;
        } catch {
          // 忽略解析错误
        }
      }

      setError(errorMessage);
      setStatus('error');
      
      // 5秒后重置
      setTimeout(() => {
        setStatus('idle');
        setError(null);
      }, 5000);
    }
  };

  const getButtonContent = () => {
    switch (status) {
      case 'exporting':
        return (
          <>
            <span className="export-spinner" />
            导出中...
          </>
        );
      case 'success':
        return (
          <>
            <span className="export-icon">✓</span>
            导出成功
          </>
        );
      case 'error':
        return (
          <>
            <span className="export-icon">✕</span>
            {error || '导出失败'}
          </>
        );
      default:
        return (
          <>
            <span className="export-icon">📥</span>
            导出 DOCX
          </>
        );
    }
  };

  return (
    <button
      className={`export-button export-${status}`}
      onClick={handleExport}
      disabled={disabled || status === 'exporting'}
      title={error || '导出为 Word 文档'}
    >
      {getButtonContent()}
    </button>
  );
};

export default ExportButton;
