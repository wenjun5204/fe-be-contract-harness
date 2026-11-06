#!/usr/bin/env python3
"""测试执行闭环(Stage 8 内循环)的确定性核心:执行 → 解析 → 门控。

设计对齐 coverage_collector.py 范式:
- 解析部分纯函数、确定性可测(支持 jest / vitest 输出);
- 执行部分薄封装(复用 tool_sandbox 白名单,不开参数化口子);
- 门控部分 fail-closed:解析不出数字按失败处理,不放过。

修复循环(诊断/修复为 LLM 阶段)在 runner 内编排,本模块只负责
"跑一次测试 → 结构化 test_report"这一步。
"""
from __future__ import annotations

import re
from typing import List

# jest/vitest 摘要行的两种口径:
#   "Tests:       3 failed, 4 passed, 7 total"(jest 冒号 + 逗号)
#   "Test Files  2 passed (2)" / "Tests  3 failed | 4 passed (7)"(vitest 空格分隔)
# 匹配两种:冒号可选;行内数字统计统一由 _COUNT_RE 提取。
_SUMMARY_RE = re.compile(
    r"^[ \t]*(Tests?|Test Files?)\s*:?\s+(.+)$", re.MULTILINE
)
_COUNT_RE = re.compile(r"(\d+)\s+(passed|failed|skipped|todo)", re.IGNORECASE)

# maven surefire 摘要行(真实首跑发现:java 栈 ./mvnw test 的输出 jest/vitest
# 解析器不认,摘要全部丢失 → parsed=False 被误判失败):
#   逐类: [INFO] Tests run: 7, Failures: 0, Errors: 0, Skipped: 0, Time elapsed: ... -- in com.x.X
#   汇总: [INFO] Tests run: 23, Failures: 0, Errors: 0, Skipped: 0
# 失败时同型行以 [ERROR] 输出,两种级别都认;汇总行(行尾无 "-- in")优先,
# 缺汇总(如输出被截断)时退化为逐类求和,仍可机验。
_SUREFIRE_RE = re.compile(
    r"^\[(?:INFO|ERROR)\]\s+Tests run:\s*(\d+),\s*Failures:\s*(\d+),"
    r"\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+)(.*)$",
    re.MULTILINE,
)


def _parse_surefire(output: str):
    """maven surefire 摘要解析;无 surefire 行返回 None(交回 jest/vitest 解析)。

    语义映射:failed = Failures + Errors(断言失败与运行异常都是失败用例);
    passed = run - failed - skipped;total = run(跑到的用例数)。
    """
    aggregate = None
    per_class_total = per_class_failed = per_class_skipped = 0
    has_surefire = False
    for m in _SUREFIRE_RE.finditer(output):
        has_surefire = True
        run, failures, errors, skipped = (int(m.group(i)) for i in range(1, 5))
        if "-- in" not in m.group(5):
            # 汇总行:取最后一条(多模块/多命令输出时末条为全局汇总)
            aggregate = (run, failures + errors, skipped)
        else:
            per_class_total += run
            per_class_failed += failures + errors
            per_class_skipped += skipped
    if not has_surefire:
        return None
    if aggregate is not None:
        run, failed, skipped = aggregate
    else:
        run, failed, skipped = per_class_total, per_class_failed, per_class_skipped
    passed = max(run - failed - skipped, 0)
    return {"total": run, "passed": passed, "failed": failed, "skipped": skipped, "parsed": True}


def parse_test_summary(output: str) -> dict:
    """从测试命令输出解析用例统计。

    先试 maven surefire 格式(java),命中即返回;否则回落 jest/vitest。
    只取 "Tests" 行的语义(用例数);"Test Files" 行不计入(文件数 ≠ 用例数),
    jest/vitest 两种格式都覆盖。返回 {total, passed, failed, skipped, parsed}。
    parsed=False 表示输出里找不到 Tests 摘要行(如命令没跑起来、
    输出被截断掉了摘要)——按 fail-closed 处理,由 gate 判失败。
    """
    surefire = _parse_surefire(output)
    if surefire is not None:
        return surefire
    counts = {"passed": 0, "failed": 0, "skipped": 0, "todo": 0}
    parsed = False
    for m in _SUMMARY_RE.finditer(output):
        if m.group(1).lower() != "tests":
            continue  # Test Files 行:不计入用例统计
        parsed = True
        for cm in _COUNT_RE.finditer(m.group(2)):
            counts[cm.group(2).lower()] += int(cm.group(1))
    return {
        "total": sum(counts.values()),
        "passed": counts["passed"],
        "failed": counts["failed"],
        "skipped": counts["skipped"] + counts["todo"],
        "parsed": parsed,
    }


def parse_failures(output: str, limit: int = 20) -> List[dict]:
    """提取失败用例条目(尽力而为,供诊断归因输入)。

    匹配用例级失败标题:
    - jest: "● Suite › case name"(● 后跟 suite > case,取 › 右侧用例名)
    - vitest: "✕ case name"(✕ 前缀)
    - maven surefire: "[ERROR]   Class.method:line message"(
      失败详情块内的行,case 取 "Class.method")
    文件级 FAIL 行不是用例,丢弃。返回 [{case}](截断到 limit 条)。
    """
    failures: List[dict] = []
    seen = set()
    for m in re.finditer(
        r"^[ \t]*(?:●|✕|×)\s+(?:(\S.*?)\s+›\s+)?(.+?)\s*$",
        output,
        re.MULTILINE,
    ):
        suite, case = m.group(1), m.group(2)
        if not case or case in seen or case.startswith("Test"):
            continue
        seen.add(case)
        failures.append({"case": case[:200], **({"suite": suite[:120]} if suite else {})})
        if len(failures) >= limit:
            break
    if failures:
        return failures
    # surefire 失败详情块:"[ERROR]   GroupServiceTest.testFoo:24 expected: ..."
    for m in re.finditer(
        r"^\[ERROR\]\s+(\S+):(\d+)\s+\S+.*$",
        output,
        re.MULTILINE,
    ):
        case = m.group(1)
        if case in seen:
            continue
        seen.add(case)
        failures.append({"case": case[:200]})
        if len(failures) >= limit:
            break
    return failures


def build_test_report(stack: str, results: List[dict]) -> dict:
    """把沙箱多命令执行结果聚合为单栈 test_report。

    results 来自 tool_sandbox.run_whitelisted(kind="test") 的 results 列表。
    fail-closed:任何命令非零退出、超时、错误,或摘要解析不出(parsed=False),
    都计入 failed_reasons;最终 ok 由 check_test_report 门控裁决。
    """
    agg = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
    failures: List[dict] = []
    reasons: List[str] = []
    parsed_any = False
    for r in results:
        cmd = r.get("command", "")
        if r.get("timeout"):
            reasons.append(f"命令超时被 kill: {cmd}")
            continue
        if r.get("error"):
            reasons.append(f"命令异常: {cmd}: {r['error']}")
            continue
        summary = parse_test_summary(r.get("output", ""))
        if not summary["parsed"]:
            # 无摘要:退出码即结论(非零=有失败,零=可能没跑用例,按可疑处理)
            if r.get("exit_code") == 0:
                reasons.append(f"输出无测试摘要(疑似未跑用例): {cmd}")
            else:
                reasons.append(f"输出无测试摘要且退出码非零: {cmd}")
                agg["failed"] += 1
            continue
        parsed_any = parsed_any or summary["parsed"]
        for k in ("total", "passed", "failed", "skipped"):
            agg[k] += summary[k]
        failures.extend(parse_failures(r.get("output", "")))
    return {
        "stack": stack,
        "summary": {**agg, "parsed": parsed_any or not reasons},
        "failures": failures,
        "failed_reasons": reasons,
    }


def check_test_report(report: dict) -> dict:
    """测试门控(fail-closed):全绿才 ok。

    判失败的条件(任一):
    - failed > 0;
    - parsed=False(含 failed_reasons 非空)——数字都拿不到,不能放行;
    - total=0——没有用例被执行,不能放行("写了用例"≠"跑了用例")。
    """
    s = report.get("summary", {})
    problems: List[str] = []
    if s.get("failed", 0) > 0:
        problems.append(f"存在失败用例: {s['failed']} 个")
    if not s.get("parsed", False):
        problems.append("测试输出无摘要,无法确认结果")
        problems.extend(report.get("failed_reasons", []))
    if s.get("total", 0) == 0:
        problems.append("无用例被执行(total=0)")
    return {"ok": not problems, "problems": problems}


def execute_tests(stack: str, repo_path: str, timeout: int = 120) -> dict:
    """执行一栈测试并产出 test_report(薄封装,复用沙箱白名单)。"""
    from lib.tool_sandbox import run_whitelisted
    ran = run_whitelisted("test", stack, repo_path, timeout=timeout)
    report = build_test_report(stack, ran.get("results", []))
    report["exit_code"] = ran.get("exit_code")
    report["command_results"] = [
        {k: r[k] for k in ("command", "exit_code") if k in r}
        for r in ran.get("results", [])
    ]
    report["gate"] = check_test_report(report)
    report["ok"] = report["gate"]["ok"]
    return report


def run_all(stacks: List[str], repo_path: str, timeout: int = 120) -> dict:
    """多栈执行 → 汇总报告。单栈环境不可用(如无该栈工程)不阻断其他栈,
    但计入 problems(最终仍 fail-closed,除非显式豁免该栈)。"""
    per_stack = {}
    problems: List[str] = []
    for s in stacks:
        try:
            r = execute_tests(s, repo_path, timeout=timeout)
        except Exception as e:  # noqa: BLE001 —— 环境类错误如实记录
            r = {
                "stack": s, "ok": False,
                "summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "parsed": False},
                "failures": [], "failed_reasons": [f"执行异常: {e}"],
            }
            r["gate"] = check_test_report(r)
        per_stack[s] = r
        if not r["ok"]:
            problems.append(f"{s}: {'; '.join(r['gate']['problems'])}")
    return {
        "per_stack": per_stack,
        "ok": not problems,
        "problems": problems,
    }


if __name__ == "__main__":
    import argparse
    import json
    import sys

    p = argparse.ArgumentParser(description="测试执行(白名单沙箱)")
    p.add_argument("stack")
    p.add_argument("repo")
    p.add_argument("--timeout", type=int, default=120)
    args = p.parse_args()
    result = execute_tests(args.stack, args.repo, timeout=args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ok"] else 1)
