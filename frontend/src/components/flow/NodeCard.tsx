import React, { useState } from 'react';
import type { NodeRun } from '@/types';
import './NodeCard.css';

interface NodeCardProps {
  node: NodeRun;
}

const NODE_LABELS: Record<string, string> = {
  controller: '中控澄清',
  attachment: '附件分析',
  writer: '文档撰写',
  image: '图片生成',
  mermaid: 'Mermaid 校对',
  diagram: '图文助手',
  assembler: '全文整合',
};

const STATUS_LABELS: Record<string, string> = {
  success: '成功',
  fail: '失败',
  running: '运行中',
  pending: '等待中',
  partial: '部分成功',
};

export const NodeCard: React.FC<NodeCardProps> = ({ node }) => {
  const [expanded, setExpanded] = useState(false);

  const label = NODE_LABELS[node.node_type] || node.node_type;
  const statusLabel = STATUS_LABELS[node.status] || node.status;

  return (
    <div className={`node-card node-card--${node.status}`}>
      <div className="node-card-header" onClick={() => setExpanded(!expanded)}>
        <div className="node-card-title">
          <span className="node-card-label">{label}</span>
          <span className={`node-card-status node-card-status--${node.status}`}>
            {statusLabel}
          </span>
        </div>
        <button className="node-card-expand">
          {expanded ? '收起' : '展开'}
        </button>
      </div>

      {expanded && (
        <div className="node-card-body">
          {/* 节点提示词规格（node_prompt_spec） */}
          {node.prompt_spec && (
            <div className="node-card-section">
              <h4>提示词规格</h4>
              <div className="node-card-spec">
                {node.prompt_spec.goal && (
                  <div className="spec-item">
                    <span className="spec-label">目标：</span>
                    <span className="spec-value">{node.prompt_spec.goal}</span>
                  </div>
                )}
                {node.prompt_spec.constraints && node.prompt_spec.constraints.length > 0 && (
                  <div className="spec-item">
                    <span className="spec-label">约束：</span>
                    <ul className="spec-list">
                      {node.prompt_spec.constraints.map((c: string, i: number) => (
                        <li key={i}>{c}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {node.prompt_spec.materials && node.prompt_spec.materials.length > 0 && (
                  <div className="spec-item">
                    <span className="spec-label">参考材料：</span>
                    <ul className="spec-list">
                      {node.prompt_spec.materials.map((m: string, i: number) => (
                        <li key={i}>{m.slice(0, 100)}...</li>
                      ))}
                    </ul>
                  </div>
                )}
                {node.prompt_spec.output_format && (
                  <div className="spec-item">
                    <span className="spec-label">输出格式：</span>
                    <span className="spec-value">{node.prompt_spec.output_format}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 执行结果 */}
          {node.result && (
            <div className="node-card-section">
              <h4>执行结果</h4>
              <pre className="node-card-result">
                {JSON.stringify(node.result, null, 2)}
              </pre>
            </div>
          )}

          {/* 错误信息 */}
          {node.error && (
            <div className="node-card-section node-card-section--error">
              <h4>错误信息</h4>
              <div className="node-card-error">
                <p><strong>类型：</strong>{node.error.error_type}</p>
                <p><strong>消息：</strong>{node.error.error_message}</p>
                {node.error.retry_guidance && (
                  <p><strong>重试指导：</strong>{node.error.retry_guidance}</p>
                )}
              </div>
            </div>
          )}

          {/* 时间戳 */}
          {node.timestamp && (
            <div className="node-card-timestamp">
              {new Date(node.timestamp).toLocaleString()}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default NodeCard;
