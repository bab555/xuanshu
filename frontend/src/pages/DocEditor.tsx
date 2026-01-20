import { useEffect, useState, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiService } from '@/services/api';
import { ThreeColumnLayout } from '@/components/layout/ThreeColumnLayout';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { FlowPanel } from '@/components/flow/FlowPanel';
import { PreviewPanel } from '@/components/preview/PreviewPanel';
import type { DocumentDetail, NodeRun, WSEvent, ChatMessage } from '@/types';
import './DocEditor.css';

export function DocEditor() {
  const { docId } = useParams<{ docId: string }>();
  const navigate = useNavigate();
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [nodeRuns, setNodeRuns] = useState<NodeRun[]>([]);
  const [activeStepIndex, setActiveStepIndex] = useState(-1);
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const wsRunIdRef = useRef<string | null>(null);

  // 流式输出状态
  const [streamingThinking, setStreamingThinking] = useState('');
  const [streamingContent, setStreamingContent] = useState('');
  const [planText, setPlanText] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingDraft, setStreamingDraft] = useState('');
  const [streamingFinal, setStreamingFinal] = useState('');
  const [isExecuting, setIsExecuting] = useState(false);

  // 抄送弹窗
  const [shareOpen, setShareOpen] = useState(false);
  const [shareUsername, setShareUsername] = useState('');
  const [shareUsers, setShareUsers] = useState<Array<{ user_id: string; username: string }>>([]);
  const [shareUsersLoading, setShareUsersLoading] = useState(false);
  const [shareNote, setShareNote] = useState('');
  const [shareSubmitting, setShareSubmitting] = useState(false);

  const applyChatHistoryFromDocVars = (docVars: any) => {
    const history = docVars?.chat_history;
    if (Array.isArray(history) && history.length > 0) {
      setChatHistory(history);
    }
  };


  useEffect(() => {
    if (docId) {
      loadDoc();
    }

    return () => {
      // 清理 WebSocket 连接
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [docId]);

  const loadDoc = async () => {
    try {
      const res = await apiService.docs.get(docId!);
      setDoc(res.data);
      // 从文档变量中恢复聊天历史
      const vars = res.data.latest_version?.doc_variables;
      applyChatHistoryFromDocVars(vars);
      if (vars?.plan_md) {
        setPlanText(String(vars.plan_md));
      }
      // 恢复最近一次运行节点（用于底部小灯/状态）
      if (res.data?.latest_run?.node_runs) {
        setNodeRuns(res.data.latest_run.node_runs);
      }
      // 恢复步骤指针（如果存在）
      if (typeof vars?.current_step_index === 'number') {
        setActiveStepIndex(vars.current_step_index);
      } else {
        setActiveStepIndex(-1);
      }
    } catch (err) {
      console.error('加载文档失败', err);
      navigate('/my');
    } finally {
      setLoading(false);
    }
  };

  const connectWebSocket = useCallback((runId: string, mode: 'plan' | 'execute' = 'plan') => {
    // 关闭现有连接
    if (wsRef.current) {
      wsRef.current.close();
    }

    // 重置流式状态
    setStreamingThinking('');
    setStreamingContent('');
    setIsStreaming(false);
    setStreamingDraft('');
    setStreamingFinal('');
    // 连接到 execute 流时，保持“执行中”状态，避免右侧在首 token 前显示旧正文造成误解
    setIsExecuting(mode === 'execute');
    wsRunIdRef.current = runId;

    const ws = apiService.workflow.stream(runId);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('WebSocket 已连接');
    };

    ws.onmessage = (event) => {
      // 处理 ping/pong 心跳响应（纯文本，非 JSON）
      if (event.data === 'pong') {
        return;
      }
      
      try {
        const msg: WSEvent = JSON.parse(event.data);
        handleWSMessage(msg);
      } catch (err) {
        console.error('解析 WebSocket 消息失败', err);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket 错误', error);
      // 按产品原则：不做兜底假成功，明确提示用户链路失败
      setIsProcessing(false);
      setIsStreaming(false);
      alert('网络波动导致连接中断（WebSocket）。请刷新页面后重试。');
    };

    ws.onclose = () => {
      console.log('WebSocket 已关闭');
    };

    // 心跳
    const heartbeat = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send('ping');
      } else {
        clearInterval(heartbeat);
      }
    }, 30000);

    return () => {
      clearInterval(heartbeat);
      ws.close();
    };
  }, []);

  const handleWSMessage = (msg: WSEvent) => {
    switch (msg.event) {
      case 'connected':
        // 初始状态
        if (msg.data.node_runs) {
          setNodeRuns(msg.data.node_runs);
        }
        // 恢复聊天历史
        applyChatHistoryFromDocVars(msg.data.doc_variables);
        // 恢复 Plan（如果有）
        if (msg.data.doc_variables?.plan_md) {
          setPlanText(String(msg.data.doc_variables.plan_md));
        }
        break;

      case 'node_update':
        // 更新节点状态
        setNodeRuns((prev) => {
          const existing = prev.find((n) => n.node_type === msg.data.node);
          if (existing) {
            return prev.map((n) =>
              n.node_type === msg.data.node
                ? { ...n, status: msg.data.status, prompt_spec: msg.data.prompt_spec }
                : n
            );
          } else {
            return [
              ...prev,
              {
                node_type: msg.data.node,
                status: msg.data.status,
                prompt_spec: msg.data.prompt_spec,
                timestamp: new Date().toISOString(),
              },
            ];
          }
        });
        // 如果是 thinking 状态，开始流式显示
        if (msg.data.status === 'thinking') {
          setIsStreaming(true);
        }
        break;

      // 流式输出事件
      case 'stream_thinking':
        setStreamingThinking((prev) => prev + msg.data.content);
        break;

      case 'stream_content':
        // Plan 阶段：对话回复流（左侧）
        setStreamingContent((prev) => prev + msg.data.content);
        break;

      case 'stream_plan':
        // Plan 阶段：计划流（中间）
        setPlanText((prev) => prev + msg.data.content);
        break;

      case 'stream_done':
        setIsStreaming(false);
        break;

      case 'stream_writer':
        setIsExecuting(true);
        setStreamingDraft((prev) => prev + msg.data.content);
        break;

      case 'stream_final_reset':
        setIsExecuting(true);
        setStreamingFinal('');
        break;

      case 'stream_final':
        setIsExecuting(true);
        setStreamingFinal((prev) => prev + msg.data.content);
        break;

      case 'chapter_update':
        setIsExecuting(true);
        if (typeof msg.data?.index === 'number') {
          setActiveStepIndex(msg.data.index);
        }
        break;

      case 'run_cancelled':
        setIsProcessing(false);
        setIsStreaming(false);
        setIsExecuting(false);
        console.warn('已停止输出');
        break;

      case 'ack_stop':
        // no-op
        break;

      case 'run_complete':
        setIsProcessing(false);
        setIsStreaming(false);
        setIsExecuting(false);
        setStreamingThinking('');
        setStreamingContent('');
        // 注意：Plan 文本不清空，便于用户确认后点击“开始执行”
        setStreamingDraft('');
        setStreamingFinal('');
        // 回填完整对话（如果后端在 doc_variables 里维护了 chat_history）
        applyChatHistoryFromDocVars(msg.data.doc_variables);
        // Plan：优先从 doc_variables.plan_md 回填（避免 controller 非流式/非 JSON 导致中间栏为空）
        if (msg.data?.doc_variables?.plan_md) {
          setPlanText(String(msg.data.doc_variables.plan_md));
        }
        // 刷新文档
        loadDoc();
        break;

      case 'run_error':
        setIsProcessing(false);
        setIsStreaming(false);
        setIsExecuting(false);
        setStreamingThinking('');
        // Plan 文本保留，便于排查；如需清空可由用户再发送一条消息触发 reset
        // setPlanText('');
        console.error('工作流错误', msg.data.error);
        break;

      case 'error':
        console.error('服务器错误', msg.data.message);
        break;
    }
  };

  const handleExecute = async () => {
    if (!docId) return;
    setIsProcessing(true);
    setIsExecuting(true);
    setStreamingDraft('');
    setNodeRuns([]);
    try {
      const res = await apiService.workflow.execute(docId);
      connectWebSocket(res.data.run_id, 'execute');
    } catch (e) {
      console.error('开始执行失败', e);
      setIsProcessing(false);
      setIsExecuting(false);
    }
  };

  const handleStop = () => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    try {
      ws.send(JSON.stringify({ event: 'client_stop', data: { run_id: wsRunIdRef.current } }));
    } catch (e) {
      console.warn('发送 stop 失败', e);
    }
  };

  const handleSendMessage = async (message: string, attachments: string[]) => {
    if (!docId) return;

    // 添加用户消息到聊天历史
    const userMsg: ChatMessage = { role: 'user', content: message, attachments };
    setChatHistory((prev) => [...prev, userMsg]);
    setIsProcessing(true);
    
    // 重置流式状态
    setStreamingThinking('');
    setPlanText('');
    setStreamingDraft('');
    setIsExecuting(false);

    try {
      // 调用对话接口
      const res = await apiService.workflow.chat(docId, {
        user_message: message,
        attachments,
      });

      setNodeRuns([]); // 清空之前的节点运行记录

      // 连接 WebSocket
      connectWebSocket(res.data.run_id, 'plan');
    } catch (err) {
      console.error('发送失败', err);
      setIsProcessing(false);
      setIsExecuting(false);
    }
  };

  const openShare = () => {
    setShareOpen(true);
    setShareUsername('');
    setShareNote('');
    setShareUsersLoading(true);
    apiService.users
      .list()
      .then((res) => setShareUsers(res.data.users || []))
      .catch((e) => {
        console.error('加载用户列表失败', e);
        setShareUsers([]);
      })
      .finally(() => setShareUsersLoading(false));
  };

  const submitShare = async () => {
    if (!docId) return;
    if (!shareUsername.trim()) return;
    setShareSubmitting(true);
    try {
      await apiService.docs.share(docId, shareUsername.trim(), shareNote.trim() || undefined);
      setShareOpen(false);
      // 简单反馈
      alert(`已抄送给 ${shareUsername.trim()}`);
      // 刷新文档详情（shares 列表）
      loadDoc();
    } catch (err) {
      console.error('抄送失败', err);
      alert('抄送失败：请检查用户名是否存在，或稍后重试');
    } finally {
      setShareSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="doc-editor-loading">
        <div className="loading-spinner" />
        <p>加载中...</p>
      </div>
    );
  }

  if (!doc) {
    return null;
  }

  const liveMd = streamingFinal || streamingDraft;
  const contentMd = (isExecuting && liveMd) 
    ? liveMd 
    : (doc.latest_version?.content_md || '');
  const docVariables = doc.latest_version?.doc_variables || {};
  const steps: string[] = Array.isArray(docVariables.outline) ? docVariables.outline.map(String) : [];

  return (
    <div className="doc-editor">
      <header className="doc-editor-header">
        <button className="btn btn-secondary" onClick={() => navigate('/my')}>
          ← 返回
        </button>
        <h1 className="doc-editor-title">{doc.title}</h1>
        <div className="doc-editor-actions">
          <span className={`doc-status status-${doc.status}`}>{doc.status}</span>
          {isProcessing && <span className="processing-indicator">处理中...</span>}
          <button className="btn btn-secondary" onClick={openShare}>
            抄送
          </button>
        </div>
      </header>

      {shareOpen && (
        <div className="modal-backdrop" onMouseDown={() => !shareSubmitting && setShareOpen(false)}>
          <div className="modal" onMouseDown={(e) => e.stopPropagation()}>
            <div className="modal-title">抄送文档</div>
            <div className="modal-body">
              <label className="modal-label">对方用户名</label>
              <select
                className="input"
                value={shareUsername}
                onChange={(e) => setShareUsername(e.target.value)}
                disabled={shareSubmitting || shareUsersLoading}
              >
                <option value="">{shareUsersLoading ? '加载中...' : '请选择用户'}</option>
                {shareUsers.map((u) => (
                  <option key={u.user_id} value={u.username}>
                    {u.username}
                  </option>
                ))}
              </select>
              <label className="modal-label" style={{ marginTop: 12 }}>备注（可选）</label>
              <textarea
                className="input"
                value={shareNote}
                onChange={(e) => setShareNote(e.target.value)}
                placeholder="例如：请帮忙评审第2章"
                disabled={shareSubmitting}
                style={{ minHeight: 80, resize: 'vertical' }}
              />
            </div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setShareOpen(false)} disabled={shareSubmitting}>
                取消
              </button>
              <button
                className="btn btn-primary"
                onClick={submitShare}
                disabled={shareSubmitting || !shareUsername.trim()}
              >
                {shareSubmitting ? '提交中...' : '确认抄送'}
              </button>
            </div>
          </div>
        </div>
      )}

      <ThreeColumnLayout
        left={
          <ChatPanel
            docId={docId!}
            docVariables={docVariables}
            chatHistory={chatHistory}
            onSendMessage={handleSendMessage}
            isProcessing={isProcessing}
            streamingThinking={streamingThinking}
            streamingContent={streamingContent}
            isStreaming={isStreaming}
          />
        }
        middle={
          <FlowPanel
            nodeRuns={nodeRuns}
            planText={planText}
            steps={steps}
            activeStepIndex={activeStepIndex}
            isExecuting={isExecuting || isProcessing}
            onExecute={handleExecute}
            onStop={handleStop}
          />
        }
        right={<PreviewPanel docId={docId!} content={contentMd} />}
      />
    </div>
  );
}
