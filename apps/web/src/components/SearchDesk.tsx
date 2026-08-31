import { useMemo, useState } from "react";
import { Alert, Button, Empty, Input, Segmented, Space, Spin, Tag, Typography } from "antd";
import { Background, Controls, ReactFlow, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { api } from "../api";
import type { Citation, ProjectContext, RelationPath, RetrievalHit } from "../types";

const { Paragraph, Text, Title } = Typography;

interface SearchDeskProps {
  project: ProjectContext;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "检索失败，请稍后重试";
}

function locatorLabel(locator: Record<string, unknown>): string {
  const entries = Object.entries(locator);
  return entries.length ? entries.map(([key, value]) => `${key}: ${String(value)}`).join(" · ") : "未提供定位信息";
}

function buildGraph(hits: RetrievalHit[]): { nodes: Node[]; edges: Edge[] } {
  const nodesById = new Map<string, Node>();
  const edgesById = new Map<string, Edge>();
  let nodeIndex = 0;
  for (const hit of hits) {
    if (!nodesById.has(hit.subject_id)) {
      nodesById.set(hit.subject_id, {
        id: hit.subject_id,
        position: { x: (nodeIndex % 3) * 240, y: Math.floor(nodeIndex / 3) * 120 },
        data: { label: hit.subject_title },
        style: { color: "#272622", background: "#fffdf7", border: "1px solid #36584f", borderRadius: 2, padding: 12, width: 190 },
      });
      nodeIndex += 1;
    }
    for (const relation of hit.relations) {
      if (!nodesById.has(relation.source_id)) {
        nodesById.set(relation.source_id, {
          id: relation.source_id,
          position: { x: (nodeIndex % 3) * 240, y: Math.floor(nodeIndex / 3) * 120 },
          data: { label: relation.source_title },
          style: { color: "#272622", background: "#fffdf7", border: "1px solid #b8863d", borderRadius: 2, padding: 12, width: 190 },
        });
        nodeIndex += 1;
      }
      if (!nodesById.has(relation.target_id)) {
        nodesById.set(relation.target_id, {
          id: relation.target_id,
          position: { x: (nodeIndex % 3) * 240, y: Math.floor(nodeIndex / 3) * 120 },
          data: { label: relation.target_title },
          style: { color: "#272622", background: "#fffdf7", border: "1px solid #b8863d", borderRadius: 2, padding: 12, width: 190 },
        });
        nodeIndex += 1;
      }
      if (!edgesById.has(relation.relation_id)) {
        edgesById.set(relation.relation_id, {
          id: relation.relation_id,
          source: relation.source_id,
          target: relation.target_id,
          label: `${relation.relation_type} · ${relation.direction}`,
          style: { stroke: "#36584f" },
          labelStyle: { fill: "#36584f", fontSize: 11 },
          animated: false,
        });
      }
    }
  }
  return { nodes: [...nodesById.values()], edges: [...edgesById.values()] };
}

export function SearchDesk({ project }: SearchDeskProps) {
  const [query, setQuery] = useState("");
  const [expandRelations, setExpandRelations] = useState(false);
  const [hits, setHits] = useState<RetrievalHit[]>([]);
  const [selectedCitation, setSelectedCitation] = useState<Citation>();
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<string>();
  const graph = useMemo(() => buildGraph(hits), [hits]);

  async function search() {
    if (!project.projectId) {
      setNotice("请先在导入中心完成一次导入，以获得 project_id。");
      return;
    }
    if (!query.trim()) {
      setNotice("请输入要检索的问题或关键词。");
      return;
    }
    setLoading(true);
    setNotice(undefined);
    try {
      const result = await api.searchRetrieval({
        projectId: project.projectId,
        query: query.trim(),
        expandRelations,
      });
      setHits(result.hits);
      setSelectedCitation(undefined);
    } catch (error: unknown) {
      setNotice(errorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="desk-section" aria-labelledby="search-title">
      <div className="section-heading">
        <div>
          <Text className="section-kicker">RETRIEVAL / P8</Text>
          <Title id="search-title" level={2}>知识检索</Title>
          <Paragraph>先看到结论，再沿着 Citation 和关系路径回到原始材料。</Paragraph>
        </div>
        <Space wrap>
          <Tag color={project.projectId ? "green" : "gold"}>{project.projectId ? "项目已绑定" : "需要 project_id"}</Tag>
          <Button onClick={() => void search()} loading={loading}>执行检索</Button>
        </Space>
      </div>

      {notice ? <Alert closable className="desk-alert" type="error" message={notice} onClose={() => setNotice(undefined)} showIcon /> : null}
      <div className="search-bar">
        <Input.Search value={query} onChange={(event) => setQuery(event.target.value)} onSearch={() => void search()} enterButton="检索" placeholder="例如：后端岗位需要哪些 Python 能力？" loading={loading} />
        <Segmented value={expandRelations ? "expand" : "focused"} onChange={(value) => setExpandRelations(value === "expand")} options={[{ label: "只看命中", value: "focused" }, { label: "展开关系", value: "expand" }]} />
      </div>

      {loading ? <div className="search-loading"><Spin tip="正在召回知识与证据…" /></div> : hits.length ? (
        <div className="search-workspace">
          <div className="search-results">
            <div className="rail-caption"><Text>知识命中</Text><span>{hits.length.toString().padStart(2, "0")}</span></div>
            <div className="hit-stack">
              {hits.map((hit, index) => <article className="hit-card" key={hit.claim_id}>
                <div className="hit-card-meta"><span>0{index + 1}</span><Tag color="green">score {hit.score.toFixed(3)}</Tag><Text type="secondary">{hit.subject_title}</Text></div>
                <p className="hit-statement">{hit.statement}</p>
                <div className="citation-list">
                  {hit.evidence.length ? hit.evidence.map((citation) => <button type="button" className={`citation-chip ${selectedCitation?.citation_id === citation.citation_id ? "is-active" : ""}`} key={citation.citation_id} onClick={() => setSelectedCitation(citation)}><strong>Citation</strong><span>{citation.source_title}</span><small>{locatorLabel(citation.locator)}</small></button>) : <Alert type="warning" message="该命中没有返回 Citation" showIcon />}
                </div>
                {hit.relations.length ? <div className="relation-strip"><Text type="secondary">关系路径</Text>{hit.relations.map((relation) => <Tag key={relation.relation_id}>{relation.source_title} — {relation.relation_type} → {relation.target_title}</Tag>)}</div> : null}
              </article>)}
            </div>
          </div>
          <aside className="search-inspector">
            <div className="column-label">02 / TRACE BACK</div>
            {selectedCitation ? <div className="citation-inspector"><Tag color="gold">{selectedCitation.source_title}</Tag><Title level={3}>引用定位</Title><blockquote>{selectedCitation.quote}</blockquote><div className="locator-card"><Text type="secondary">稳定定位信息</Text><strong>{locatorLabel(selectedCitation.locator)}</strong><small>source_version_id · {selectedCitation.source_version_id}</small></div><Alert type="info" message="原文预览接口待接入" description="当前已保留来源、版本和 locator；待后端提供文件流/消息读取接口后，可在此精确打开原文。" showIcon /></div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="点击任意 Citation 查看回溯信息" />}
          </aside>
        </div>
      ) : query ? <Empty className="search-empty" description="没有命中可展示的知识或证据" /> : <Empty className="search-empty" description="输入问题，开始查看带证据的知识命中" />}

      {hits.length && graph.edges.length ? <section className="graph-panel" aria-labelledby="graph-title"><div className="graph-panel-heading"><div><Text className="section-kicker">TOPOLOGY / LOCAL VIEW</Text><Title id="graph-title" level={3}>当前结果关系图</Title></div><Text type="secondary">仅展示本次检索返回的关系</Text></div><div className="graph-canvas"><ReactFlow nodes={graph.nodes} edges={graph.edges} fitView minZoom={0.45} maxZoom={1.4} nodesDraggable={false}><Background color="#d9d0bd" gap={24} /><Controls /></ReactFlow></div></section> : null}
    </section>
  );
}
