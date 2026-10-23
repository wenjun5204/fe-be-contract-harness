# regressions/ —— 失败 transcript 采集池(外循环 E1)

## 这是什么

`--live` 阶段失败时,`llm_dispatch` 自动把完整 transcript 落盘到 `.pending/`
(文件名:`<UTC时间戳>-stage<sid>-<原因摘要>.json`)。这是**未筛选素材**,
`.pending/` 已 gitignore,永不直接进 CI。

## 筛选流程(脚本采集、人筛选、脚本重放)

```
失败 → .pending/<ts>-stage8-空转.json     (脚本,自动)
     → 人工看一遍,三类处置:
        ① 新失败模式 → 浓缩成 evals/replay_gates.py 的一个场景(带断言)
        ② 契约形态问题 → 加一个 evals/cases/<name>.yaml + expected.json
        ③ 噪音/重复 → 直接删
     → 沉淀后删除 .pending/ 原始文件
```

## 为什么不自动进 CI

回流数据是运行时产物(模型不可信输入);不筛选直接重放会让 CI 被临时性
失败(网络抖动/脚本耗尽)刷红。筛选是人类职责,重放是脚本职责——
见 docs/ARCHITECTURE.md「双循环」章节。
