"""agentkit.eval CLI — run eval suites and diff scorecards from the shell.

Usage:
    python -m agentkit.eval run <cases-path> \
        --app <module:func> \
        [--mode scripted|live] \
        [--json scorecard.json] \
        [--md   scorecard.md]

    python -m agentkit.eval diff <prev.json> <new.json>

The --app argument names a Python function with signature
`(llm: LLMClient) -> App` (e.g. `chatcfd_plugin.eval_setup:build_eval_app`).
Plugin authors expose one such function per eval target.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import sys
from pathlib import Path

from agentkit.eval.case import load_cases
from agentkit.eval.live import EvalMode, resolve_mode, run_cases
from agentkit.eval.scorecard import Scorecard


def _resolve_builder(spec: str):
    mod_name, _, fn_name = spec.partition(":")
    if not mod_name or not fn_name:
        raise SystemExit(f"--app expects module:func, got {spec!r}")
    sys.path.insert(0, str(Path.cwd()))
    mod = importlib.import_module(mod_name)
    fn = getattr(mod, fn_name, None)
    if fn is None:
        raise SystemExit(f"{mod_name} has no attribute {fn_name}")
    return fn


def _cmd_run(args: argparse.Namespace) -> int:
    cases = load_cases(args.cases_path)
    if not cases:
        print(f"no cases found in {args.cases_path}", file=sys.stderr)
        return 2
    builder = _resolve_builder(args.app)
    mode = resolve_mode(args.mode)
    results = asyncio.run(run_cases(cases, builder, mode=mode, live_model=args.model))
    card = Scorecard(results)
    print(card.to_markdown(title=f"{args.cases_path} ({mode.value})"))
    if args.json:
        card.write(json_path=args.json)
    if args.md:
        card.write(md_path=args.md)
    return 0 if card.failed == 0 else 1


def _cmd_diff(args: argparse.Namespace) -> int:
    prev = json.loads(Path(args.prev).read_text(encoding="utf-8"))
    new = json.loads(Path(args.new).read_text(encoding="utf-8"))
    prev_by_id = {r["case_id"]: r["passed"] for r in prev.get("results", [])}
    new_by_id = {r["case_id"]: r["passed"] for r in new.get("results", [])}
    regressed: list[str] = []
    fixed: list[str] = []
    added: list[str] = []
    removed: list[str] = []
    for cid, pr in prev_by_id.items():
        if cid not in new_by_id:
            removed.append(cid)
            continue
        if pr and not new_by_id[cid]:
            regressed.append(cid)
        elif not pr and new_by_id[cid]:
            fixed.append(cid)
    for cid in new_by_id:
        if cid not in prev_by_id:
            added.append(cid)
    print(
        f"# Eval Diff\n"
        f"- prev: {prev['passed']}/{prev['total']}\n"
        f"- new:  {new['passed']}/{new['total']}\n"
    )
    for label, items in (("Regressed", regressed), ("Fixed", fixed),
                        ("Added", added), ("Removed", removed)):
        if items:
            print(f"\n## {label} ({len(items)})")
            for i in items:
                print(f"- {i}")
    return 1 if regressed else 0


def _force_utf8_stdio() -> None:
    """Windows shells default to GBK/cp1252; markdown output contains ✅/❌."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(prog="agentkit.eval")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Run an eval suite")
    p_run.add_argument("cases_path", help="Path to a .yaml file or directory of .yaml files")
    p_run.add_argument("--app", required=True, help="module:func returning App from (llm)")
    p_run.add_argument("--mode", choices=["scripted", "live"], default=None)
    p_run.add_argument("--model", help="LLM model id (for live mode)")
    p_run.add_argument("--json", help="Write JSON scorecard here")
    p_run.add_argument("--md", help="Write Markdown scorecard here")
    p_run.set_defaults(func=_cmd_run)

    p_diff = sub.add_parser("diff", help="Diff two scorecard JSON files")
    p_diff.add_argument("prev")
    p_diff.add_argument("new")
    p_diff.set_defaults(func=_cmd_diff)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
