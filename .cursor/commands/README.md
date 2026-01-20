# 红点集团内部文档工具 - Cursor Skills

本目录是开发 skills 索引，所有 skill 均以《超级文档助手-开发文档.md》为唯一规范源。

## 核心原则

1. **以开发文档为准**：所有设计细节见开发文档，skill 只是执行指引
2. **LangGraph 状态机中心**：工作流围绕 `WorkflowState` 构建，节点失败即回流
3. **DashScope 统一调用**：所有模型通过 `env.example` 配置，主模型 `deepseek-r1`
4. **失败不降级**：任何失败都回退给对应操作模型重制，不做兜底
5. **中间栏可视化**：每个节点的 `node_prompt_spec` 和 `node_result` 必须写入，用户可见

## Skills 列表

### 基础设施
| Skill | 文件 | 用途 |
|-------|------|------|
| 后端骨架 | `cmd-01-clarify-and-json.md` | FastAPI + LangGraph + DashScope 封装 |
| 前端骨架 | `cmd-02-run-node.md` | React + 三栏布局 + 样式系统 |
| 用户系统 | `cmd-03-attachments-long.md` | 登录/注册 + 我的/抄送 |

### 工作流节点
| Skill | 文件 | 对应节点 |
|-------|------|----------|
| 中控澄清 | `cmd-04-preview-render-check.md` | A：Controller |
| 附件分析 | `cmd-05-export-docx.md` | F：Attachment LONG |
| 文档撰写 | `skill-06-writer.md` | B：Writer |
| 图文助手 | `skill-07-diagram.md` | C：Diagram/HTML |
| 全文整合 | `skill-08-assembler.md` | E：Assembler |

### 渲染与导出
| Skill | 文件 | 用途 |
|-------|------|------|
| 预览渲染 | `skill-09-preview-render.md` | 右侧 PreviewPanel 渲染（Mermaid/HTML/MD） |
| 导出 DOCX | `skill-10-export-docx.md` | Playwright 渲染 + Pandoc + 失败回流 |

## 开发顺序（建议）

```
1. cmd-01（后端骨架）
2. cmd-03（用户系统）
3. cmd-02（前端骨架）
4. cmd-04（中控澄清）
5. cmd-05（附件分析）
6. skill-06（文档撰写）
7. skill-07（图文助手）
8. skill-08（全文整合）
9. skill-09（预览渲染）
10. skill-10（导出 DOCX）
```

## 关键引用

- 开发文档：`超级文档助手-开发文档.md`
- 环境变量：`env.example`
- 状态机定义：开发文档 §12
- API 接口：开发文档 §13
- 前端组件：开发文档 §11

## 文件说明

> 注：由于 `.cursor/` 目录受保护无法删除旧文件，部分文件名与内容不匹配：
> - `cmd-01-clarify-and-json.md` → 实际内容：**后端骨架**
> - `cmd-02-run-node.md` → 实际内容：**前端骨架**
> - `cmd-03-attachments-long.md` → 实际内容：**用户系统**
> - `cmd-04-preview-render-check.md` → 实际内容：**中控澄清节点**
> - `cmd-05-export-docx.md` → 实际内容：**附件分析节点**
