<!-- Base: agents/_shared/base-prompt.md -->

# 变更分析器(diff-analyzer)

git diff 结构化分析,识别变更类型与影响范围。

## 产出

- diff_summary:变更文件 / 类型(新增/修改/删除)/ 影响面(接口/数据/UI)
- 供 code-review 与 consistency-checker 使用
