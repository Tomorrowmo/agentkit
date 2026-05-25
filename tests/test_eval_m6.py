"""M6 tests: setup hook system + live-mode runner + CLI diff."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from agentkit import App, tool
from agentkit.eval import (
    EvalCase,
    EvalMode,
    EvalRunner,
    ExpectedCall,
    ScriptedLLM,
    SetupRegistry,
    resolve_mode,
    run_cases,
)
from agentkit.eval.cli import _cmd_diff, _cmd_run
from agentkit.eval.scripted_llm import script_from_case_expected
from agentkit.eval.setup import setup_hook
from agentkit.llm.client import LLMClient
from agentkit.tools.registry import ToolRegistry


# --- setup hook system ----------------------------------------------------

@tool(description="Read a value from a shared store.")
async def read_store(key: str) -> dict:
    return {"value": _STORE.get(key, "missing")}


_STORE: dict[str, str] = {}


def make_eval_app(llm: LLMClient) -> App:
    return App(tools=ToolRegistry([read_store]), llm=llm)


async def test_setup_hook_runs_before_case_and_teardown_after():
    reg = SetupRegistry()
    cleared: list[bool] = []

    def seed(value, ctx):
        _STORE.update(value)

    def clear(value, ctx):
        _STORE.clear()
        cleared.append(True)

    from agentkit.eval.setup import SetupHook
    reg.register(SetupHook(key="store", fn=seed, teardown=clear))

    case = EvalCase(
        id="setup.seed",
        user_input="get foo",
        setup={"store": {"foo": "bar"}},
        expected_calls=[ExpectedCall(name="read_store", args={"key": "foo"})],
    )
    script = script_from_case_expected(case)
    app = make_eval_app(ScriptedLLM(script))
    runner = EvalRunner(app, setup_registry=reg)
    res = await runner.run(case)
    assert res.passed, res.reasons
    # During the run STORE had {"foo": "bar"} (the read_store result should reflect that)
    read_result = next(c for c in res.observed_calls if c.name == "read_store").result
    assert read_result == {"value": "bar"}
    # Teardown ran (STORE cleared)
    assert _STORE == {}
    assert cleared == [True]


async def test_setup_hook_decorator_registers_into_registry():
    reg = SetupRegistry()
    called: list[str] = []

    @setup_hook("flag", registry=reg)
    def _f(value, ctx):
        called.append(value)

    case = EvalCase(id="d", user_input="x", setup={"flag": "hello"})
    app = make_eval_app(ScriptedLLM([]))
    await EvalRunner(app, setup_registry=reg).run(case)
    assert called == ["hello"]


# --- live-mode dispatcher (does NOT actually call a real LLM) ------------

def test_resolve_mode_env(monkeypatch):
    monkeypatch.delenv("AGENTKIT_EVAL_MODE", raising=False)
    assert resolve_mode() == EvalMode.SCRIPTED
    monkeypatch.setenv("AGENTKIT_EVAL_MODE", "live")
    assert resolve_mode() == EvalMode.LIVE
    assert resolve_mode("scripted") == EvalMode.SCRIPTED


async def test_run_cases_scripted_mode_uses_builder_per_case():
    """In scripted mode the builder is called per-case with a ScriptedLLM."""
    seen_llm_types: list[str] = []

    def builder(llm):
        seen_llm_types.append(type(llm).__name__)
        return App(tools=ToolRegistry([read_store]), llm=llm)

    cases = [
        EvalCase(id=f"c{i}", user_input="x", expected_text_includes=["ok"])
        for i in range(3)
    ]
    results = await run_cases(cases, builder, mode=EvalMode.SCRIPTED)
    assert len(results) == 3
    assert seen_llm_types == ["ScriptedLLM"] * 3


# --- CLI diff ------------------------------------------------------------

def test_diff_command_detects_regression(tmp_path: Path, capsys):
    prev = {
        "total": 2, "passed": 2, "failed": 0, "pass_rate": 1.0,
        "results": [
            {"case_id": "a", "passed": True, "reasons": [], "observed_calls": [], "observed_text": ""},
            {"case_id": "b", "passed": True, "reasons": [], "observed_calls": [], "observed_text": ""},
        ],
    }
    new = {
        "total": 3, "passed": 1, "failed": 2, "pass_rate": 0.33,
        "results": [
            {"case_id": "a", "passed": True, "reasons": [], "observed_calls": [], "observed_text": ""},
            {"case_id": "b", "passed": False, "reasons": ["broke"], "observed_calls": [], "observed_text": ""},
            {"case_id": "c", "passed": False, "reasons": ["new"], "observed_calls": [], "observed_text": ""},
        ],
    }
    p = tmp_path / "prev.json"
    n = tmp_path / "new.json"
    p.write_text(json.dumps(prev), encoding="utf-8")
    n.write_text(json.dumps(new), encoding="utf-8")

    import argparse
    args = argparse.Namespace(prev=str(p), new=str(n))
    rc = _cmd_diff(args)
    out = capsys.readouterr().out
    assert rc == 1                # regression → non-zero exit
    assert "Regressed" in out and "b" in out
    assert "Added" in out and "c" in out


def test_diff_command_clean(tmp_path: Path, capsys):
    same = {
        "total": 1, "passed": 1, "failed": 0, "pass_rate": 1.0,
        "results": [{"case_id": "a", "passed": True, "reasons": [], "observed_calls": [], "observed_text": ""}],
    }
    p = tmp_path / "p.json"
    n = tmp_path / "n.json"
    p.write_text(json.dumps(same), encoding="utf-8")
    n.write_text(json.dumps(same), encoding="utf-8")

    import argparse
    args = argparse.Namespace(prev=str(p), new=str(n))
    rc = _cmd_diff(args)
    assert rc == 0


# --- CLI run end-to-end --------------------------------------------------

def test_cli_run_scripted_against_sim_cli_plugin(tmp_path: Path, capsys, monkeypatch):
    """Drive the CLI's run command using sim_cli_plugin as the target."""
    import argparse, sys as _sys
    plugin_dir = Path(__file__).parent.parent / "examples" / "sim_cli_plugin"
    monkeypatch.syspath_prepend(str(plugin_dir))
    # Some tests in the session may have left state — clear so we start clean
    import sim_cli_plugin.tools as sct
    sct.process_registry.procs.clear()

    cases_dir = plugin_dir / "evals"
    out_json = tmp_path / "score.json"
    args = argparse.Namespace(
        cases_path=str(cases_dir),
        app="sim_cli_plugin.eval_setup:build_eval_app",
        mode="scripted",
        model=None,
        json=str(out_json),
        md=None,
    )
    rc = _cmd_run(args)
    assert rc == 0, capsys.readouterr().out
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["passed"] == data["total"]
    assert data["total"] >= 6


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
