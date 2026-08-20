#!/usr/bin/env python3
"""契约驱动生成 CLI。

用法:
    python3 lib/contract/cli.py generate examples/petstore.yaml --stack node --out gen/node
    python3 lib/contract/cli generate examples/petstore.yaml --stack react --out gen/react
    python3 lib/contract/cli.py verify examples/petstore.yaml --stack node
    python3 lib/contract/cli.py stacks
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

# 使 `python3 lib/contract/cli.py` 直接执行时也能 import lib.* 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.contract.generator import generate, write_out  # noqa: E402
from lib.contract.verify import verify  # noqa: E402
from lib.stack.adapter import available  # noqa: E402


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(description="契约驱动代码生成")
    sub = p.add_subparsers(dest="cmd")

    g = sub.add_parser("generate", help="从契约生成代码")
    g.add_argument("contract")
    g.add_argument("--stack", required=True)
    g.add_argument("--out", required=True)

    v = sub.add_parser("verify", help="G1 生成门校验")
    v.add_argument("contract")
    v.add_argument("--stack", required=True)

    sub.add_parser("stacks", help="列出可用技术栈")

    args = p.parse_args(argv)

    if args.cmd == "generate":
        files = write_out(args.contract, args.stack, args.out)
        print(json.dumps({"ok": True, "stack": args.stack, "files": files}, ensure_ascii=False, indent=2))
    elif args.cmd == "verify":
        result = verify(args.contract, args.stack)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1
    elif args.cmd == "stacks":
        print(json.dumps(available(), ensure_ascii=False))
    else:
        p.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
