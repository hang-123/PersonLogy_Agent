import { useState } from "react";
import { Alert, Button, Empty, Input, Space, Spin, Tag, Typography } from "antd";

import { api } from "../api";
import type { Citation, EvidenceDetail, ProjectContext, RetrievalAnswerResponse } from "../types";

const { Paragraph, Text, Title } = Typography;

interface AnswerDeskProps {
  project: ProjectContext;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "问答失败，请稍后重试";
}

function locatorLabel(locator: Record<string, unknown>): string {
  const entries = Object.entries(locator);
  return entries.length ? entries.map(([key, value]) => `${key}: ${String(value)}`).join(" · ") : "未提供定位信息";
}

export function AnswerDesk({ project }: AnswerDeskProps) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<RetrievalAnswerResponse>();
  const [selectedCitation, setSelectedCitation] = useState<Citation>();
  const [evidence, setEvidence] = useState<EvidenceDetail>();
  const [loading, setLoading] = useState(false);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [notice, setNotice] = useState<string>();

  async function ask() {
    if (!project.projectId) {
      setNotice("请先在导入中心完成一次导入，以获得 project_id。");
      return;
    }
    if (!question.trim()) {
      setNotice("请输入想核验的问题。");
      return;
    }
    setLoading(true);
    setNotice(undefined);
    try {
      setResult(await api.answerRetrieval({ projectId: project.projectId, question: question.trim(), expandRelations: true }));
      setSelectedCitation(undefined);
      setEvidence(undefined);
    } catch (error: unknown) {
      setNotice(errorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  async function inspectCitation(citation: Citation) {
    setSelectedCitation(citation);
    setEvidence(undefined);
    setEvidenceLoading(true);
    try {
      if (!project.projectId) return;
      setEvidence(await api.getEvidence(citation.citation_id, project.projectId));
    } catch (error: unknown) {
      setNotice(`Evidence 详情读取失败：${errorMessage(error)}`);
    } finally {
      setEvidenceLoading(false);
    }
  }

  return (
    <section className="desk-section" aria-labelledby="answer-title">
      <div className="section-heading">
        <div>
          <Text className="section-kicker">ANSWER / P9</Text>
          <Title id="answer-title" level={2}>带来源问答</Title>
          <Paragraph>答案只由当前项目的检索结果支撑；每条结论都可以继续打开 Evidence 和原文。</Paragraph>
        </div>
        <Space wrap>
          <Tag color={project.projectId ? "green" : "gold"}>{project.projectId ? "项目已绑定" : "需要 project_id"}</Tag>
          <Tag color="blue">retrieval-grounded</Tag>
        </Space>
      </div>

      {notice ? <Alert closable className="desk-alert" type="error" message={notice} onClose={() => setNotice(undefined)} showIcon /> : null}
      <div className="answer-bar">
        <Input.Search value={question} onChange={(event) => setQuestion(event.target.value)} onSearch={() => void ask()} enterButton="提问" placeholder="例如：哪些结论已经有来源支持？" loading={loading} />
        <Button onClick={() => void ask()} loading={loading}>生成带来源回答</Button>
      </div>

      {loading ? <div className="search-loading"><Spin tip="正在检索结论、证据与关系…" /></div> : result ? <div className="answer-workspace">
          <div className="answer-main">
          <div className="answer-meta"><Tag color="blue">{result.mode}</Tag><Text type="secondary">{result.hit_count} 条结论 · {result.citations.length} 条来源</Text></div>
          <div className="answer-card"><Text className="section-kicker">GROUNDED RESPONSE</Text><p>{result.answer}</p></div>
          {result.uncertainty.length ? <Alert type="warning" showIcon message="需要继续核验" description={<ul>{result.uncertainty.map((item) => <li key={item}>{item}</li>)}</ul>} /> : <Alert type="success" showIcon message="当前回答的命中结论均带有 Citation" />}
          <div className="answer-section"><div className="rail-caption"><Text>来源证据</Text><span>{result.citations.length.toString().padStart(2, "0")}</span></div><div className="citation-list">{result.citations.map((citation) => <button type="button" className={`citation-chip ${selectedCitation?.citation_id === citation.citation_id ? "is-active" : ""}`} key={citation.citation_id} onClick={() => void inspectCitation(citation)}><strong>Citation</strong><span>{citation.source_title}</span><small>{locatorLabel(citation.locator)}</small></button>)}</div></div>
          {result.relations.length ? <div className="answer-section"><div className="rail-caption"><Text>关系路径</Text><span>{result.relations.length.toString().padStart(2, "0")}</span></div><div className="relation-strip">{result.relations.map((relation) => <Tag key={relation.relation_id}>{relation.source_title} · {relation.relation_type} → {relation.target_title}</Tag>)}</div></div> : null}
        </div>
        <aside className="answer-inspector search-inspector"><div className="column-label">02 / SOURCE DETAIL</div>{selectedCitation ? <div className="citation-inspector"><Tag color="gold">{selectedCitation.source_title}</Tag><Title level={3}>Evidence 详情</Title>{evidenceLoading ? <Spin size="small" tip="正在读取来源正文…" /> : null}<blockquote>{evidence?.quote ?? selectedCitation.quote}</blockquote><div className="locator-card"><Text type="secondary">稳定定位信息</Text><strong>{locatorLabel(evidence?.locator ?? selectedCitation.locator)}</strong></div>{evidence ? <><div className="source-preview"><Text type="secondary">来源正文 · block {evidence.content_block.ordinal + 1}</Text><p>{evidence.content_block.content}</p></div>{project.projectId ? <Button type="link" href={api.sourceVersionContentUrl(evidence.source_version.id, project.projectId)} target="_blank" rel="noreferrer">打开 PDF 原文 ↗</Button> : null}</> : null}</div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="点击来源证据查看正文" />}</aside>
      </div> : <Empty className="search-empty" description="输入问题，开始获取带来源的回答" />}
    </section>
  );
}
