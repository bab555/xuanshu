import { MarkdownRenderer } from '../preview/MarkdownRenderer';
import type { NodeRun } from '@/types';
import './FlowPanel.css';

interface Props {
  nodeRuns: NodeRun[];
  planText?: string;
  steps?: string[];
  activeStepIndex?: number;
  isExecuting?: boolean;
  onExecute?: () => void;
  onStop?: () => void;
}

export function FlowPanel({
  nodeRuns,
  planText = '',
  steps = [],
  activeStepIndex = -1,
  isExecuting = false,
  onExecute,
  onStop,
}: Props) {
  const canExecute = !!planText && !isExecuting;
  const currentNode = [...nodeRuns].reverse().find((n) => n.status === 'running')?.node_type;
  return (
    <div className="flow-panel">
      <div className="flow-header">
        <h3>工作流状态</h3>
        <div className="flow-header-right">
          <span className="flow-count">{currentNode ? `当前：${currentNode}` : `${nodeRuns.length} 个节点`}</span>
          <div className="flow-actions">
            <button
              className="btn btn-primary btn-sm"
              onClick={onExecute}
              disabled={!onExecute || !canExecute}
              title="在计划确认后，开始执行撰写/图文/整合"
            >
              {isExecuting ? '执行中...' : '开始执行'}
            </button>
            <button
              className="btn btn-secondary btn-sm"
              onClick={onStop}
              disabled={!onStop || !isExecuting}
              title="停止当前输出"
            >
              停止输出
            </button>
          </div>
        </div>
      </div>

      <div className="flow-content">
        <div className="flow-plan-card">
          <div className="flow-plan-title">计划（Plan）</div>
          <div className="flow-plan-body">
            {planText ? (
              <div className="flow-plan-markdown">
                <MarkdownRenderer content={planText} />
              </div>
            ) : (
              <div className="flow-plan-empty">发送消息后，中控会在这里生成撰写指南/大纲/计划</div>
            )}
          </div>
        </div>

        <div className="flow-indicator-bar" title="章节/skills 执行进度">
          {steps.length === 0 ? (
            <div className="flow-indicator-empty">等待 Plan 生成大纲后显示进度灯</div>
          ) : (
            <div className="flow-indicators">
              {steps.map((t, idx) => {
                const state =
                  activeStepIndex === idx ? 'active' : activeStepIndex > idx ? 'done' : 'idle';
                return (
                  <div key={`${idx}-${t}`} className="flow-indicator-item" title={t}>
                    <span className={`flow-indicator-dot ${state}`} />
                    <span className="flow-indicator-label">{idx + 1}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
