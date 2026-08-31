import { useEffect, useState } from "react";
import { Button, Input, Space, Tag, Typography } from "antd";

import type { ProjectContext } from "../types";

const { Text } = Typography;

interface ProjectContextBarProps {
  value: ProjectContext;
  onChange: (value: ProjectContext) => void;
}

export function ProjectContextBar({ value, onChange }: ProjectContextBarProps) {
  const [draft, setDraft] = useState(value);

  useEffect(() => setDraft(value), [value]);

  function save() {
    onChange({
      projectName: draft.projectName.trim(),
      projectSlug: draft.projectSlug.trim(),
      projectId: draft.projectId,
    });
  }

  function clearId() {
    const next = { ...draft, projectId: undefined };
    setDraft(next);
    onChange(next);
  }

  return (
    <section className="project-context-bar" aria-label="项目上下文">
      <div className="project-context-copy">
        <Text className="context-kicker">PROJECT CONTEXT</Text>
        <strong>先确定材料归属，再开始导入</strong>
        <small>项目名称和 slug 会随 PDF / 对话导入提交。</small>
      </div>
      <div className="project-context-fields">
        <Input
          aria-label="项目名称"
          placeholder="项目名称"
          value={draft.projectName}
          onChange={(event) => setDraft({ ...draft, projectName: event.target.value })}
        />
        <Input
          aria-label="项目 slug"
          placeholder="project-slug"
          value={draft.projectSlug}
          onChange={(event) => setDraft({ ...draft, projectSlug: event.target.value })}
        />
        <Button onClick={save}>保存</Button>
        {value.projectId ? (
          <Space size={6}>
            <Tag color="green">已绑定 project_id</Tag>
            <Button type="text" size="small" onClick={clearId}>
              清除
            </Button>
          </Space>
        ) : (
          <Tag>首次导入后绑定</Tag>
        )}
      </div>
    </section>
  );
}
