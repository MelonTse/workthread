# 旧规则与知识导入

旧项目不修改。只接受经授权的脱敏 JSON 导出文件，不读取旧数据库路径，不导入附件和凭证。真实 11 一级／32 二级分类尚未提供，当前仅验证接口。

```json
{
  "schema_version":"1.0",
  "categories":[{"id":"group","name":"合成一级"},{"id":"child","parent_id":"group","name":"合成二级"}],
  "customers":[{"id":"c","name":"Synthetic customer"}],
  "contacts":[{"id":"p","name":"Demo","address":"demo@example.org","customer_id":"c"}],
  "relations":[{"from_id":"p","to_id":"c","relation":"contact","confirmed":false}],
  "cases":[{"id":"o","title":"Synthetic order","case_type":"order","customer_id":"c","stage":"pending"}],
  "profile":{"english_style":"short paragraphs"},
  "knowledge":[{"scope":"customer","subject_id":"c","content":"合成客户规则","confirmed":false}]
}
```

字段映射：旧分类 ID→categories；人物与企业→contacts/customers/relations；项目与订单→cases；风格与习惯→personal 知识；客户特殊要求→customer；一次性要求→case。没有已确认标记默认候选；profile 导入也先候选。仅明确的 confirmed=true 保留确认状态，不根据模型置信度自动升级。

CLI：`workthread --workspace <目录> legacy-import export.json` 预览；增加 `--apply` 执行。HTTP POST /api/v1/legacy/import 的 document 为上述数据，apply 默认 false。重复导入幂等，响应 batch_id 保存映射。POST /api/v1/legacy/<batch_id>/undo 可撤销；记录已修改或被其他业务引用时拒绝删除，保留现有数据。
