for item in {
  ('is_a', '是一个', '类型继承或分类关系', true),
  ('part_of', '属于', '组成或从属关系', true),
  ('depends_on', '依赖', '前置依赖关系', true),
  ('supports', '支持', '证据或论点支持关系', true),
  ('contradicts', '冲突', '结论互相冲突', false),
  ('related_to', '相关', '通用相关关系', false),
  ('derived_from', '派生自', '知识由另一知识派生', true),
}
union (
  insert RelationType {
    key := item.0,
    label := item.1,
    description := item.2,
    directional := item.3,
  }
  unless conflict on .key
);
