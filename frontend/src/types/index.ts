// 用户
export interface User {
  user_id: string;
  username: string;
}

// 文档
export interface Document {
  doc_id: string;
  title: string;
  status: string;
  updated_at: string;
}

export interface DocumentDetail {
  doc_id: string;
  title: string;
  status: string;
  owner: User;
  latest_version: {
    version_id: string;
    content_md: string;
    doc_variables: Record<string, any>;
  } | null;
  workflow_runs: WorkflowRun[];
  latest_run?: {
    run_id: string;
    status: string;
    current_node?: string;
    node_runs: NodeRun[];
  } | null;
  shares: Array<{ to_user: string; shared_at: string }>;
}

// 附件
export interface Attachment {
  attachment_id: string;
  filename: string;
  file_type?: string;
  url: string;
  analysis_status: string;
  summary?: string;
}

// 工作流
export interface WorkflowRun {
  run_id: string;
  status: string;
  current_node?: string;
  started_at: string;
  ended_at?: string;
}

export interface NodePromptSpec {
  node_type: string;
  goal: string;
  constraints: string[];
  materials: string[];
  output_format: string;
  variables_snapshot: Record<string, any>;
  attachments_snapshot: Attachment[];
}

export interface ErrorInfo {
  error_type: string;
  error_message: string;
  block_id?: string;
  block_source?: string;
  retry_guidance: string;
}

export interface NodeRun {
  node_type: string;
  status: 'pending' | 'running' | 'success' | 'fail' | 'partial';
  prompt_spec?: NodePromptSpec;
  result?: any;
  error?: ErrorInfo;
  timestamp: string;
}

// 节点类型
export type NodeType =
  | 'controller'
  | 'writer'
  | 'diagram'
  | 'image'
  | 'checker'
  | 'assembler'
  | 'attachment'
  | 'export';

export const NODE_LABELS: Record<NodeType, string> = {
  controller: 'A：中控对话',
  writer: 'B：文档撰写',
  diagram: 'C：图文助手',
  image: 'D：生图助手',
  checker: 'E：终审校验',
  assembler: 'E：全文整合',
  attachment: 'F：附件分析',
  export: 'X：导出',
};

// 聊天消息
export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  attachments?: string[];
}

// WebSocket 事件
export interface WSEvent {
  event: 
    | 'connected' 
    | 'run_start' 
    | 'node_update' 
    | 'run_complete' 
    | 'run_error' 
    | 'error'
    | 'stream_thinking'  // 思考过程增量
    | 'stream_content'   // 回复内容增量
    | 'stream_plan'      // Plan（Markdown）增量
    | 'stream_done'      // 流式输出完成
    | 'stream_writer'    // 撰写草稿增量
    | 'stream_final_reset' // 终审流式开始前清空
    | 'stream_final'     // 终审最终正文增量
    | 'chapter_update'   // 章节/skills 小灯进度
    | 'run_cancelled'    // 用户停止输出
    | 'ack_stop';        // 服务端确认停止
  data: any;
}
