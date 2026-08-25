#!/usr/bin/env python3
"""仓库知识提取自测。运行:python3 tests/test_repo_knowledge.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.repo_knowledge import (  # noqa: E402
    build_knowledge,
    detect_stack,
    save,
    scaffold,
    validate_knowledge,
    validate_repo,
)


def _repo(root: Path, package_json=True) -> Path:
    (root / ".git").mkdir()
    if package_json:
        (root / "package.json").write_text('{"dependencies": {"react": "^18"}}', encoding="utf-8")
    return root


def test_validate_detect_and_build():
    with tempfile.TemporaryDirectory() as d:
        repo = _repo(Path(d))
        (repo / "src").mkdir()
        (repo / "src" / "App.tsx").write_text("export default function App() {}", encoding="utf-8")
        validation = validate_repo(repo)
        assert validation["ok"] and "package.json" in validation["dependency_files"], validation
        assert detect_stack(str(repo))["react"] is True
        knowledge = build_knowledge(str(repo))
        assert "react" in knowledge and "package.json" in knowledge and "src" in knowledge


def test_invalid_or_low_confidence_repo():
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d)
        assert not validate_repo(repo)["ok"], "无 .git 的目录不应通过严格校验"
        _repo(repo, package_json=False)
        validation = validate_repo(repo)
        assert validation["ok"] and validation["warnings"], validation


def test_save():
    with tempfile.TemporaryDirectory() as d:
        repo = _repo(Path(d))
        output = save(str(repo), repo / "kb")
        assert output.exists()
        assert "# 仓库知识" in output.read_text(encoding="utf-8")


def test_scaffold_modes_and_knowledge_validation():
    with tempfile.TemporaryDirectory() as d:
        repo = _repo(Path(d))
        first = scaffold(str(repo), "demo")
        assert first["created"]
        scripts = list((repo / ".agents" / "scripts").glob("*.sh"))
        assert len(scripts) == 4
        script = repo / ".agents" / "scripts" / "inject_context.sh"
        original = script.read_text(encoding="utf-8")
        assert "demo" in original
        script.write_text("custom script", encoding="utf-8")
        second = scaffold(str(repo), "demo", mode="create")
        assert script.read_text(encoding="utf-8") == "custom script"
        assert ".agents/scripts/inject_context.sh" in second["skipped"]
        third = scaffold(str(repo), "demo", mode="replace")
        assert "demo" in script.read_text(encoding="utf-8")
        assert ".agents/scripts/inject_context.sh" in third["replaced"]
        incomplete = validate_knowledge(repo)
        assert not incomplete["ok"] and "AGENTS.md" in incomplete["placeholders"]
        for rel in ("AGENTS.md", ".agents/docs/architecture.md", ".agents/docs/conventions.md", ".agents/docs/domain-model.md"):
            (repo / rel).write_text("# completed\n", encoding="utf-8")
        complete = validate_knowledge(repo)
        assert complete["ok"], complete


def main():
    test_validate_detect_and_build()
    test_invalid_or_low_confidence_repo()
    test_save()
    test_scaffold_modes_and_knowledge_validation()
    print("OK: repo_knowledge 自测通过(4 组断言)")


if __name__ == "__main__":
    main()
