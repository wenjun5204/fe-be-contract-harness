---
{
  "domain": "backend",
  "entity": "CodegenDrift",
  "error_codes": [],
  "fields": [],
  "id": "drift-node-petstore",
  "source": "drift_check",
  "states": [],
  "status": "assumption",
  "type": "convention",
  "updated_at": "2026-10-29T01:05:05Z"
}
---

契约漂移记录(node 栈,契约 petstore.yaml):routes_drift=True, models_drift=False。期望路由 ['createPet', 'getPetById', 'listPets'] vs 磁盘 ['only_one_route']。生成产物与最新契约不一致,重新生成或人工核对差异后经 confirm 确认处理结论。
