#!/usr/bin/env python3
"""Tool Calling 工具注册表 —— 把 harness 的确定性能力暴露为 LLM 可调用工具。

设计(设计文档 §15「主 Agent 只调度」的执行层补全):
- 工具 = JSON Schema 参数(OpenAI function calling 格式)+ 执行器 + 描述
- execute_tool 做参数校验(required/type);执行器异常不炸主循环,统一返回
  {"ok": False, "error": ...} 让模型自纠错
- read_file / write_file 限定在 workspace 根内(拒绝 .. 与越界绝对路径),
  防止 Agent 越界读写
- report_outputs 是阶段收尾工具:主循环捕获其参数作为 complete_stage 的
  structured outputs(fail-closed:不调用即无法过门)

内置工具(全部包装既有确定性能力,不引入新语义):
- read_contract       解析契约,返回实体与 schema 概览
- verify_codegen      G1 生成门(契约 vs 骨架)
- consistency_check   跨栈一致性检查
- query_knowledge     领域知识检索(按 domain + 实体过滤)
- read_file/write_file workspace 范围内文件读写
- report_outputs      阶段终态产出上报

用法:
    from lib.tool_registry import build_default_tools
    tools = build_default_tools(contract_path="examples/petstore.yaml", workdir=Path("."))
    tools.schemas()          # OpenAI tools 参数
    tools.execute("read_contract", {})  # -> {"ok": True, ...}
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from lib.contract.parser import parse_contract

# JSON Schema type -> Python 类型集合(参数校验用)
_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
    "null": type(None),
}


class ToolError(Exception):
    """工具调用失败(参数或执行错误)。"""


@dataclass
class Tool:
    name: str
    description: str
    parameters: Dict[str, Any]
    fn: Callable[[Dict[str, Any]], Any]
    terminal: bool = False
    """terminal=True 表示该工具产出阶段终态结果(如 report_outputs),主循环据此收束。"""


@dataclass
class ToolRegistry:
    tools: Dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        if tool.name in self.tools:
            raise ValueError(f"工具重复注册: {tool.name}")
        self.tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        tool = self.tools.get(name)
        if tool is None:
            raise ToolError(f"未知工具: {name}(可用: {', '.join(sorted(self.tools))})")
        return tool

    def schemas(self) -> List[dict]:
        """导出 OpenAI function calling 格式的 tools 参数。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self.tools.values()
        ]

    def validate_args(self, name: str, args: Optional[dict]) -> dict:
        """按 JSON Schema 的 required/type 子集校验参数。"""
        tool = self.get(name)
        args = args if isinstance(args, dict) else {}
        schema = tool.parameters or {"type": "object", "properties": {}}
        for key in schema.get("required", []):
            if key not in args:
                raise ToolError(f"工具 {name} 缺少必填参数: {key}")
        props = schema.get("properties", {})
        for key, value in args.items():
            if key not in props:
                raise ToolError(f"工具 {name} 不接受参数: {key}(可用: {', '.join(props) or '无'})")
            expected = props[key].get("type")
            if expected and expected in _TYPE_MAP and not isinstance(value, _TYPE_MAP[expected]):
                raise ToolError(f"工具 {name} 参数 {key} 类型应为 {expected},实际 {type(value).__name__}")
        return args

    def execute(self, name: str, args: Optional[dict]) -> dict:
        """校验并执行工具;异常统一收敛为 {"ok": False, "error": ...}(供模型自纠错)。"""
        try:
            validated = self.validate_args(name, args)
            result = self.get(name).fn(validated)
            return result if isinstance(result, dict) else {"ok": True, "result": result}
        except ToolError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:  # noqa: BLE001 —— 执行器异常不炸主循环
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}


# ---- 路径安全 ----

def safe_join(workdir: Path, rel_path: str) -> Path:
    """把相对路径限制在 workdir 内;拒绝越界(../、绝对路径逃逸)。"""
    workdir = Path(workdir).resolve()
    p = Path(rel_path)
    candidate = (workdir / p).resolve() if not p.is_absolute() else p.resolve()
    if candidate != workdir and workdir not in candidate.parents:
        raise ToolError(f"路径越界(仅允许 {workdir} 内): {rel_path}")
    return candidate


# ---- 内置工具执行器 ----

def _read_contract_fn(contract_path: Optional[str], args: dict) -> dict:
    path = args.get("path") or contract_path
    if not path:
        raise ToolError("未提供契约路径(构造工具时未绑定 contract,且参数缺 path)")
    model = parse_contract(Path(path))
    schemas = model.get("schemas", {})
    return {
        "ok": True,
        "contract": str(path),
        "entities": sorted(schemas.keys()),
        "schemas": {
            name: [f.get("name", str(f)) for f in (schema.get("fields") or [])]
            for name, schema in schemas.items()
        } or schemas,
        "endpoints": [
            {k: ep.get(k) for k in ("method", "path", "request", "response", "entity") if ep.get(k)}
            for ep in model.get("endpoints", [])
        ],
    }


def _verify_codegen_fn(args: dict) -> dict:
    from lib.contract.verify import verify
    report = verify(Path(args["contract"]), args["stack"], Path(args["out_dir"]))
    return {"ok": True, "stack": args["stack"], "report": report}


def _consistency_check_fn(args: dict) -> dict:
    from lib.contract.consistency import cross_stack_check
    report = cross_stack_check(Path(args["contract"]))
    report["ok"] = report.get("ok", True)
    return report


def _query_knowledge_fn(args: dict) -> dict:
    from lib.domain_knowledge import load_entries, render_entry
    domain = args["domain"]
    entity = (args.get("entity") or "").strip()
    entries = [
        e for e in load_entries(domain)
        if e.get("status") == "confirmed"
        and (not entity or entity.lower() in json.dumps(e, ensure_ascii=False).lower())
    ]
    return {
        "ok": True,
        "domain": domain,
        "matched": len(entries),
        "entries": [render_entry(e).strip() for e in entries],
    }


def _read_file_fn(workdir: Path, args: dict) -> dict:
    path = safe_join(workdir, args["path"])
    if not path.is_file():
        raise ToolError(f"文件不存在: {args['path']}")
    return {"ok": True, "path": args["path"], "content": path.read_text(encoding="utf-8")}


def _write_file_fn(workdir: Path, args: dict) -> dict:
    path = safe_join(workdir, args["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(args["content"], encoding="utf-8")
    return {"ok": True, "path": args["path"], "bytes": len(args["content"].encode("utf-8"))}


def _report_outputs_fn(args: dict) -> dict:
    outputs = args.get("outputs")
    if not isinstance(outputs, dict) or not outputs:
        raise ToolError("report_outputs 需要非空对象参数 outputs(阶段 structured outputs)")
    return {"ok": True, "received": True, "keys": sorted(outputs.keys())}


# ---- 默认工具集构造 ----

def build_default_tools(
    contract_path: Optional[str | Path] = None,
    workdir: Optional[str | Path] = None,
) -> ToolRegistry:
    """构造 LLM 阶段默认工具集。workdir 缺省为当前目录(文件工具的边界根)。"""
    workdir = Path(workdir) if workdir else Path.cwd()
    registry = ToolRegistry()
    registry.register(Tool(
        name="read_contract",
        description="解析 OpenAPI 契约,返回实体(schema)清单、字段概览与 endpoints。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "契约文件路径;缺省用当前阶段绑定的契约"},
            },
            "required": [],
        },
        fn=lambda args: _read_contract_fn(str(contract_path) if contract_path else None, args),
    ))
    registry.register(Tool(
        name="verify_codegen",
        description="G1 生成门:校验指定技术栈的生成骨架与契约一致。",
        parameters={
            "type": "object",
            "properties": {
                "contract": {"type": "string", "description": "契约文件路径"},
                "stack": {"type": "string", "enum": ["react", "vue", "node", "java"]},
                "out_dir": {"type": "string", "description": "生成物目录"},
            },
            "required": ["contract", "stack", "out_dir"],
        },
        fn=_verify_codegen_fn,
    ))
    registry.register(Tool(
        name="consistency_check",
        description="跨栈一致性检查(前后端实现与契约的对齐报告)。",
        parameters={
            "type": "object",
            "properties": {"contract": {"type": "string"}},
            "required": ["contract"],
        },
        fn=_consistency_check_fn,
    ))
    registry.register(Tool(
        name="query_knowledge",
        description="按 domain 与实体关键词检索已确认的领域知识条目。",
        parameters={
            "type": "object",
            "properties": {
                "domain": {"type": "string", "enum": ["business", "backend", "frontend", "qa"]},
                "entity": {"type": "string", "description": "实体/关键词;缺省返回该 domain 全部"},
            },
            "required": ["domain"],
        },
        fn=_query_knowledge_fn,
    ))
    registry.register(Tool(
        name="read_file",
        description="读取 workspace 内的文件内容。",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "相对 workspace 根的路径"}},
            "required": ["path"],
        },
        fn=lambda args: _read_file_fn(workdir, args),
    ))
    registry.register(Tool(
        name="write_file",
        description="写入 workspace 内的文件(自动创建父目录)。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "相对 workspace 根的路径"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
        fn=lambda args: _write_file_fn(workdir, args),
    ))
    registry.register(Tool(
        name="report_outputs",
        description=(
            "阶段收尾(必须调用):提交本阶段 structured outputs。"
            "键名须覆盖阶段 required_outputs(如 test_cases / pr_url / deploy_result)。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "outputs": {"type": "object", "description": "阶段产出,键为 required_outputs 中的字段名"},
            },
            "required": ["outputs"],
        },
        fn=_report_outputs_fn,
        terminal=True,
    ))
    return registry


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    tools = build_default_tools("examples/petstore.yaml")
    print(json.dumps(tools.schemas(), ensure_ascii=False, indent=2))
