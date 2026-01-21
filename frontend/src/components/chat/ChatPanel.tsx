import { useState, useRef, useEffect } from 'react';
import { apiService } from '@/services/api';
import type { ChatMessage } from '@/types';
import './ChatPanel.css';

interface Props {
  docId: string;
  docVariables: Record<string, any>;
  chatHistory?: ChatMessage[];
  onSendMessage: (message: string, attachments: string[]) => void;
  isProcessing?: boolean;
  // 流式输出
  streamingThinking?: string;
  streamingContent?: string;
  streamingToolCalls?: { name: string; args: any }[]; // New prop
  isStreaming?: boolean;
}

export function ChatPanel({
  docId,
  docVariables,
  chatHistory = [],
  onSendMessage,
  isProcessing = false,
  streamingThinking = '',
  streamingContent = '',
  streamingToolCalls = [], // New prop
  isStreaming = false,
}: Props) {
  const [input, setInput] = useState('');
  const [attachments, setAttachments] = useState<{ id: string; name: string }[]>([]);
  const [uploading, setUploading] = useState(false);
  // 默认展开思考过程
  const [showThinking, setShowThinking] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory, streamingContent, streamingThinking]);

  // 当开始新的流式输出时，自动展开思考过程
  useEffect(() => {
    if (isStreaming && streamingThinking) {
      setShowThinking(true);
    }
  }, [isStreaming, streamingThinking]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      const res = await apiService.attachments.upload(docId, file);
      setAttachments((prev) => [...prev, { id: res.data.attachment_id, name: file.name }]);
    } catch (err) {
      console.error('上传失败', err);
    } finally {
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleSend = () => {
    if ((!input.trim() && attachments.length === 0) || isProcessing) return;

    // 发送消息
    onSendMessage(
      input,
      attachments.map((a) => a.id)
    );

    // 清空输入
    setInput('');
    setAttachments([]);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const removeAttachment = (id: string) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  };

  // 简单的 Markdown 渲染
  const renderMarkdown = (content: string) => {
    // 处理代码块
    const parts = content.split(/(```[\s\S]*?```)/g);
    
    return parts.map((part, index) => {
      // 代码块
      if (part.startsWith('```')) {
        const match = part.match(/```(\w*)\n?([\s\S]*?)```/);
        if (match) {
          const [, lang, code] = match;
          return (
            <pre key={index} className="code-block" data-lang={lang || 'text'}>
              <code>{code.trim()}</code>
            </pre>
          );
        }
      }
      
      // 普通文本，处理内联格式
      return (
        <span key={index}>
          {renderInlineMarkdown(part)}
        </span>
      );
    });
  };

  // 渲染内联 Markdown
  const renderInlineMarkdown = (text: string) => {
    // 分割成行
    const lines = text.split('\n');
    
    return lines.map((line, lineIndex) => {
      // 处理标题
      if (line.startsWith('### ')) {
        return <h4 key={lineIndex} className="md-h4">{line.slice(4)}</h4>;
      }
      if (line.startsWith('## ')) {
        return <h3 key={lineIndex} className="md-h3">{line.slice(3)}</h3>;
      }
      if (line.startsWith('# ')) {
        return <h2 key={lineIndex} className="md-h2">{line.slice(2)}</h2>;
      }
      
      // 处理列表
      if (line.match(/^[-*]\s/)) {
        return <li key={lineIndex} className="md-li">{renderInlineFormats(line.slice(2))}</li>;
      }
      if (line.match(/^\d+\.\s/)) {
        return <li key={lineIndex} className="md-li-numbered">{renderInlineFormats(line.replace(/^\d+\.\s/, ''))}</li>;
      }
      
      // 普通段落
      if (line.trim()) {
        return (
          <p key={lineIndex} className="md-p">
            {renderInlineFormats(line)}
          </p>
        );
      }
      
      // 空行
      return <br key={lineIndex} />;
    });
  };

  // 渲染内联格式（粗体、斜体、行内代码）
  const renderInlineFormats = (text: string) => {
    // 简化处理：只处理行内代码
    const parts = text.split(/(`[^`]+`)/g);
    
    return parts.map((part, i) => {
      if (part.startsWith('`') && part.endsWith('`')) {
        return <code key={i} className="inline-code">{part.slice(1, -1)}</code>;
      }
      // 处理粗体
      const boldParts = part.split(/(\*\*[^*]+\*\*)/g);
      return boldParts.map((bp, j) => {
        if (bp.startsWith('**') && bp.endsWith('**')) {
          return <strong key={`${i}-${j}`}>{bp.slice(2, -2)}</strong>;
        }
        return bp;
      });
    });
  };

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <h3>对话</h3>
        {Object.keys(docVariables).length > 0 && (
          <span className="chat-variables-badge">已收集 {Object.keys(docVariables).length} 项</span>
        )}
      </div>

      <div className="chat-messages">
        {chatHistory.length === 0 && !isStreaming ? (
          <div className="chat-empty">
            <div className="chat-empty-icon">💬</div>
            <p>开始对话，描述你要写的文档</p>
            <p className="chat-hint">例如：帮我写一份项目方案，主题是智能文档助手...</p>
          </div>
        ) : (
          <>
            {chatHistory.map((msg, i) => (
              <div key={i} className={`chat-message chat-message--${msg.role}`}>
                <div className="chat-message-avatar">
                  {msg.role === 'user' ? '👤' : '🤖'}
                </div>
                <div className="chat-message-bubble">
                  <div className="chat-message-content">
                    {renderMarkdown(msg.content)}
                  </div>
                  {msg.attachments && msg.attachments.length > 0 && (
                    <div className="chat-message-attachments">
                      {msg.attachments.map((id) => (
                        <span key={id} className="attachment-tag">
                          📎 附件
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {/* 流式输出显示 */}
            {isStreaming && (
              <div className="chat-message chat-message--assistant chat-message--streaming">
                <div className="chat-message-avatar">🤖</div>
                <div className="chat-message-bubble">
                  {/* 思考过程（默认展开） */}
                  {streamingThinking && (
                    <div className="thinking-section">
                      <button
                        className="thinking-toggle"
                        onClick={() => setShowThinking(!showThinking)}
                      >
                        <span className="thinking-icon">🧠</span>
                        <span>{showThinking ? '收起' : '展开'}思考过程</span>
                        <span className="thinking-indicator">
                          <span></span>
                          <span></span>
                          <span></span>
                        </span>
                      </button>
                      {showThinking && (
                        <div className="thinking-content">
                          {renderMarkdown(streamingThinking)}
                          <span className="cursor-blink thinking-cursor">▌</span>
                        </div>
                      )}
                    </div>
                  )}

                  {/* 工具调用显示 */}
                  {streamingToolCalls && streamingToolCalls.length > 0 && (
                    <div className="tool-calls-section">
                      {streamingToolCalls.map((tool, idx) => (
                        <div key={idx} className="tool-call-item">
                          <span className="tool-icon">🔧</span>
                          <span className="tool-name">正在执行: {tool.name}</span>
                          {/* <span className="tool-args">{JSON.stringify(tool.args)}</span> */}
                          <span className="tool-spinner" />
                        </div>
                      ))}
                    </div>
                  )}

                  {/* 回复内容 */}
                  {streamingContent ? (
                    <div className="chat-message-content streaming-content">
                      {renderMarkdown(streamingContent)}
                      <span className="cursor-blink">▌</span>
                    </div>
                  ) : !streamingThinking ? (
                    <div className="chat-message-content">
                      <div className="typing-indicator">
                        <span></span>
                        <span></span>
                        <span></span>
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>
            )}

            {/* 非流式处理中 */}
            {isProcessing && !isStreaming && (
              <div className="chat-message chat-message--assistant">
                <div className="chat-message-avatar">🤖</div>
                <div className="chat-message-bubble chat-message--typing">
                  <div className="typing-indicator">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      <div className="chat-input-area">
        {attachments.length > 0 && (
          <div className="chat-attachments-preview">
            {attachments.map((att) => (
              <div key={att.id} className="attachment-item">
                <span>📎 {att.name}</span>
                <button onClick={() => removeAttachment(att.id)}>×</button>
              </div>
            ))}
          </div>
        )}

        <div className="chat-input-row">
          <button
            className="chat-upload-btn"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading || isProcessing}
            title="上传文件"
          >
            {uploading ? '...' : '📎'}
          </button>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleUpload}
            style={{ display: 'none' }}
          />
          <textarea
            className="chat-input"
            placeholder={isProcessing ? '正在思考中...' : '输入消息，按 Enter 发送'}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            disabled={isProcessing}
          />
          <button
            className="chat-send-btn btn btn-primary"
            onClick={handleSend}
            disabled={isProcessing || (!input.trim() && attachments.length === 0)}
          >
            发送
          </button>
        </div>
      </div>
    </div>
  );
}
