import { useState } from "react";
import { Alert, Button, Empty, Input, Segmented, Space, Tag, Typography } from "antd";

import { api } from "../api";
import type {
  ConversationImportRequest,
  ConversationImportResponse,
  PdfImportResponse,
  ProjectContext,
} from "../types";

const { Paragraph, Text, Title } = Typography;
type ImportMode = "pdf" | "conversation";

interface ImportDeskProps {
  project: ProjectContext;
  onProjectId: (projectId: string) => void;
  onJobCreated: (jobId: string) => void;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "导入失败，请稍后重试";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function validateConversation(value: unknown): ConversationImportRequest {
  if (!isRecord(value)) throw new Error("JSON 根节点必须是对象");
  const requiredStrings = ["conversation_id", "title"];
  for (const field of requiredStrings) {
    if (typeof value[field] !== "string" || !value[field]) throw new Error(`缺少字段：${field}`);
  }
  const conversationId = value.conversation_id as string;
  const title = value.title as string;
  if (!Array.isArray(value.messages) || value.messages.length === 0) {
    throw new Error("messages 必须是至少包含一条消息的数组");
  }
  const messages = value.messages.map((item, index) => {
    if (!isRecord(item)) throw new Error(`messages[${index}] 必须是对象`);
    if (typeof item.message_id !== "string" || !item.message_id) {
      throw new Error(`messages[${index}].message_id 缺失`);
    }
    if (typeof item.role !== "string" || !item.role) throw new Error(`messages[${index}].role 缺失`);
    if (typeof item.content !== "string" || !item.content) {
      throw new Error(`messages[${index}].content 缺失`);
    }
    if (typeof item.ordinal !== "number") throw new Error(`messages[${index}].ordinal 缺失`);
    return {
      message_id: item.message_id,
      role: item.role,
      content: item.content,
      ordinal: item.ordinal,
      created_at: typeof item.created_at === "string" ? item.created_at : null,
      parent_message_id: typeof item.parent_message_id === "string" ? item.parent_message_id : null,
      attachments: Array.isArray(item.attachments)
        ? item.attachments.filter(isRecord)
        : [],
    };
  });
  return {
    project_name: "",
    project_slug: "",
    conversation_id: conversationId,
    title,
    messages,
    metadata: isRecord(value.metadata) ? value.metadata : {},
  };
}

export function ImportDesk({ project, onProjectId, onJobCreated }: ImportDeskProps) {
  const [mode, setMode] = useState<ImportMode>("pdf");
  const [pdfFile, setPdfFile] = useState<File>();
  const [pdfTitle, setPdfTitle] = useState("");
  const [conversationJson, setConversationJson] = useState("");
  const [conversationFileName, setConversationFileName] = useState("");
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<{ type: "success" | "error"; text: string }>();
  const [pdfResult, setPdfResult] = useState<PdfImportResponse>();
  const [conversationResult, setConversationResult] = useState<ConversationImportResponse>();

  const hasProject = Boolean(project.projectName.trim() && project.projectSlug.trim());

  function choosePdf(file: File | undefined) {
    setNotice(undefined);
    setPdfResult(undefined);
    if (!file) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setPdfFile(undefined);
      setNotice({ type: "error", text: "只支持 PDF 文件。" });
      return;
    }
    setPdfFile(file);
    if (!pdfTitle) setPdfTitle(file.name.replace(/\.pdf$/i, ""));
  }

  async function chooseConversation(file: File | undefined) {
    setNotice(undefined);
    setConversationResult(undefined);
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".json")) {
      setNotice({ type: "error", text: "对话导入需要 JSON 文件。" });
      return;
    }
    setConversationFileName(file.name);
    setConversationJson(await file.text());
  }

  async function submitPdf() {
    if (!hasProject) {
      setNotice({ type: "error", text: "请先保存项目名称和 project slug。" });
      return;
    }
    if (!pdfFile) {
      setNotice({ type: "error", text: "请选择要导入的 PDF 文件。" });
      return;
    }
    if (!pdfTitle.trim()) {
      setNotice({ type: "error", text: "请填写 PDF 标题。" });
      return;
    }
    setLoading(true);
    setNotice(undefined);
    try {
      const result = await api.uploadPdf({
        projectName: project.projectName.trim(),
        projectSlug: project.projectSlug.trim(),
        title: pdfTitle.trim(),
        file: pdfFile,
      });
      onProjectId(result.project_id);
      setPdfResult(result);
      onJobCreated(result.job_id);
      setNotice({ type: "success", text: result.reused_version ? "已复用相同内容的来源版本。" : "PDF 已接收，解析任务已创建。" });
    } catch (error: unknown) {
      setNotice({ type: "error", text: errorMessage(error) });
    } finally {
      setLoading(false);
    }
  }

  async function submitConversation() {
    if (!hasProject) {
      setNotice({ type: "error", text: "请先保存项目名称和 project slug。" });
      return;
    }
    let payload: ConversationImportRequest;
    try {
      payload = validateConversation(JSON.parse(conversationJson) as unknown);
      payload.project_name = project.projectName.trim();
      payload.project_slug = project.projectSlug.trim();
    } catch (error: unknown) {
      setNotice({ type: "error", text: errorMessage(error) });
      return;
    }
    setLoading(true);
    setNotice(undefined);
    try {
      const result = await api.importConversation(payload);
      onProjectId(result.project_id);
      setConversationResult(result);
      onJobCreated(result.job_id);
      setNotice({ type: "success", text: `对话已接收，导入 ${result.imported_message_count} 条消息。` });
    } catch (error: unknown) {
      setNotice({ type: "error", text: errorMessage(error) });
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="desk-section" aria-labelledby="import-title">
      <div className="section-heading">
        <div>
          <Text className="section-kicker">INGESTION / P3 + P4</Text>
          <Title id="import-title" level={2}>导入中心</Title>
          <Paragraph>先保存不可变的原始材料，再让异步任务进入解析与编译链路。</Paragraph>
        </div>
        <div className="flow-ruler" aria-label="导入流程">
          <span className="is-current">Source</span><i>→</i><span>Job</span><i>→</i><span>Review</span>
        </div>
      </div>

      {notice ? <Alert closable className="desk-alert" type={notice.type} message={notice.text} onClose={() => setNotice(undefined)} showIcon /> : null}

      <div className="import-workspace">
        <div className="import-panel import-intro-panel">
          <div className="column-label">01 / SOURCE INTAKE</div>
          <Title level={3}>把原始材料交给系统</Title>
          <Paragraph>文件只负责进入 Source 和 Job 链路，正式知识仍需经过后续审核。</Paragraph>
          <div className="import-sequence">
            <div><span>01</span><strong>保存原始材料</strong><small>保留来源版本和内容哈希</small></div>
            <div><span>02</span><strong>跟踪异步任务</strong><small>查看解析、编译和失败原因</small></div>
            <div><span>03</span><strong>进入人工审核</strong><small>机器结果不会直接发布</small></div>
          </div>
          <div className="import-note"><Tag color="gold">Evidence first</Tag><Text>每条后续结论都应能回到来源定位。</Text></div>
        </div>

        <div className="import-panel import-form-panel">
          <Segmented<ImportMode> block value={mode} onChange={setMode} options={[{ label: "PDF 文档", value: "pdf" }, { label: "对话 JSON", value: "conversation" }]} />
          {!hasProject ? <Alert className="inline-alert" type="warning" showIcon message="请先在上方保存项目上下文" /> : null}
          {mode === "pdf" ? (
            <div className="import-form-stack">
              <label className="field-label" htmlFor="pdf-title">文档标题</label>
              <Input id="pdf-title" value={pdfTitle} onChange={(event) => setPdfTitle(event.target.value)} placeholder="例如：后端工程师 JD" />
              <label className="file-dropzone" htmlFor="pdf-file">
                <input id="pdf-file" type="file" accept="application/pdf,.pdf" onChange={(event) => choosePdf(event.target.files?.[0])} />
                <span className="file-dropzone-mark">PDF</span>
                <strong>{pdfFile ? pdfFile.name : "选择或拖入 PDF 文件"}</strong>
                <small>{pdfFile ? `${(pdfFile.size / 1024 / 1024).toFixed(2)} MB` : "原始文件将进入受控导入链路"}</small>
              </label>
              <Button type="primary" size="large" loading={loading} onClick={() => void submitPdf()}>提交 PDF 导入</Button>
              {pdfResult ? <div className="import-result"><Tag color="green">已创建 Job</Tag><strong>{pdfResult.job_id}</strong><small>source {pdfResult.source_id} · {pdfResult.page_count} 页 · v{pdfResult.version}</small><Button type="link" onClick={() => onJobCreated(pdfResult.job_id)}>查看任务进度 →</Button></div> : null}
            </div>
          ) : (
            <div className="import-form-stack">
              <label className="file-dropzone compact" htmlFor="conversation-file">
                <input id="conversation-file" type="file" accept="application/json,.json" onChange={(event) => void chooseConversation(event.target.files?.[0])} />
                <span className="file-dropzone-mark">JSON</span>
                <strong>{conversationFileName || "选择对话 JSON 文件"}</strong>
                <small>也可以直接粘贴标准化对话 JSON</small>
              </label>
              <label className="field-label" htmlFor="conversation-json">对话 JSON</label>
              <Input.TextArea id="conversation-json" className="payload-editor" value={conversationJson} onChange={(event) => setConversationJson(event.target.value)} placeholder={'{"conversation_id":"…","title":"…","messages":[…]}'} autoSize={{ minRows: 10, maxRows: 18 }} />
              <Button type="primary" size="large" loading={loading} onClick={() => void submitConversation()}>提交对话导入</Button>
              {conversationResult ? <div className="import-result"><Tag color="green">已创建 Job</Tag><strong>{conversationResult.job_id}</strong><small>导入 {conversationResult.imported_message_count} 条 · 重复 {conversationResult.duplicate_message_count} 条</small><Button type="link" onClick={() => onJobCreated(conversationResult.job_id)}>查看任务进度 →</Button></div> : null}
            </div>
          )}
        </div>
      </div>

      {!hasProject && !notice ? <Empty className="import-empty-hint" image={Empty.PRESENTED_IMAGE_SIMPLE} description="保存项目上下文后即可开始导入" /> : null}
    </section>
  );
}
