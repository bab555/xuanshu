# skill-04：中控澄清节点（Controller）

> 对应开发文档：§5.1 节点 A、§12 LangGraph 状态机

## 目标

实现 A：Controller 节点：
- 引导用户澄清文档需求
- 生成/更新 `doc_variables`
- 校验完整性并追问

## 节点实现

### nodes/controller.py

```python
import json
from datetime import datetime
from app.services.model_client import model_client
from app.config import settings
from app.schemas.workflow import WorkflowState, NodePromptSpec, NodeResult

CONTROLLER_SYSTEM_PROMPT = """你是红点集团内部文档工具的中控助手。你的职责是：
1. 引导用户把"要写什么文档"说清楚
2. 将用户需求转化为结构化的文档变量（doc_variables）
3. 检查信息完整性，缺什么就追问

你必须输出 JSON 格式，包含：
- doc_variables_patch: 对文档变量的增量更新（merge patch）
- validation_report: { missing_fields: [], conflicts: [], next_questions: [] }
- reply: 给用户的自然语言回复

doc_variables 应包含：
- doc_type: 文档类型/主题
- audience: 受众与用途
- outline: 结构/大纲（数组）
- key_points: 必须包含的关键点（数组）
- materials: 可参考材料来源
- constraints: 约束（长度、风格、禁忌等）

只根据用户提供的信息填写，不要编造。目标是"说清楚一件事"，不追求好看。"""

async def run(state: WorkflowState) -> WorkflowState:
    """A：中控对话节点"""
    
    # 构造 node_prompt_spec（写入中间栏）
    prompt_spec: NodePromptSpec = {
        "node_type": "controller",
        "goal": "把用户需求澄清到可执行，形成 doc_variables",
        "constraints": [
            "只根据用户信息填写，不编造",
            "只求说清楚，不追求排版好看",
            "变量必须可被后续节点直接消费"
        ],
        "materials": [a.get("summary", "") for a in state.get("attachments", []) if a.get("summary")],
        "output_format": "JSON: doc_variables_patch + validation_report + reply",
        "variables_snapshot": state.get("doc_variables", {}),
        "attachments_snapshot": state.get("attachments", []),
    }
    
    # 构造消息
    messages = [
        {"role": "system", "content": CONTROLLER_SYSTEM_PROMPT},
    ]
    
    # 添加对话历史
    for msg in state.get("chat_history", []):
        messages.append(msg)
    
    # 添加当前变量快照
    if state.get("doc_variables"):
        messages.append({
            "role": "system",
            "content": f"当前文档变量：\n```json\n{json.dumps(state['doc_variables'], ensure_ascii=False, indent=2)}\n```"
        })
    
    # 添加附件摘要
    if prompt_spec["materials"]:
        messages.append({
            "role": "system",
            "content": f"用户上传的附件摘要：\n" + "\n".join(prompt_spec["materials"])
        })
    
    try:
        # 调用模型
        model = settings.model_controller
        response = await model_client.call(model, messages)
        
        # 解析输出
        result = parse_controller_response(response)
        
        # 合并变量
        new_variables = {**state.get("doc_variables", {}), **result.get("doc_variables_patch", {})}
        
        # 记录到 node_runs
        node_run = {
            "node_type": "controller",
            "prompt_spec": prompt_spec,
            "result": result,
            "status": "success",
            "timestamp": datetime.now().isoformat(),
        }
        
        return {
            **state,
            "doc_variables": new_variables,
            "node_runs": state.get("node_runs", []) + [node_run],
            "current_node": "controller",
            "node_status": "success",
            "error": None,
        }
        
    except Exception as e:
        # 失败处理
        node_run = {
            "node_type": "controller",
            "prompt_spec": prompt_spec,
            "result": None,
            "status": "fail",
            "error": {
                "error_type": "model_error",
                "error_message": str(e),
                "retry_guidance": "重试调用模型",
            },
            "timestamp": datetime.now().isoformat(),
        }
        
        return {
            **state,
            "node_runs": state.get("node_runs", []) + [node_run],
            "current_node": "controller",
            "node_status": "fail",
            "error": node_run["error"],
            "retry_count": state.get("retry_count", 0) + 1,
        }

def parse_controller_response(response: str) -> dict:
    """解析模型输出"""
    try:
        # 尝试提取 JSON
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0]
        else:
            json_str = response
        return json.loads(json_str)
    except:
        # 降级：返回原始回复
        return {
            "doc_variables_patch": {},
            "validation_report": {"missing_fields": [], "conflicts": [], "next_questions": []},
            "reply": response
        }
```

## 前端对接

### ChatPanel 发送消息后触发工作流

```typescript
// hooks/useChat.ts
import { api } from '@/services/api';

export function useChat(docId: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  
  const sendMessage = async (content: string, attachments?: string[]) => {
    // 添加用户消息到列表
    setMessages(prev => [...prev, { role: 'user', content }]);
    
    // 触发工作流
    const { run_id } = await api.workflow.run(docId, {
      user_message: content,
      attachments,
    });
    
    // 订阅 WebSocket 获取实时更新
    // ...
  };
  
  return { messages, sendMessage };
}
```

## 验收标准

- [ ] 用户发送消息后，Controller 节点被调用
- [ ] 模型输出被正确解析为 `doc_variables_patch` 和 `validation_report`
- [ ] `doc_variables` 被正确更新
- [ ] 中间栏能展示 `node_prompt_spec` 和节点输出
- [ ] 失败时记录错误并触发回流
