"""Tests for the eval framework itself (Case loading, Runner, Scorecard)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agentkit import App, tool
from agentkit.eval import (
    EvalCase,
    EvalRunner,
    ExpectedCall,
    Scorecard,
    ScriptedLLM,
    ScriptedTurn,
    load_cases,
)
from agentkit.eval.case import match_args
from agentkit.protocol.messages import ToolCall
from agentkit.tools.registry import ToolRegistry


# --- helpers --------------------------------------------------------------

@tool(description="Echo back.")
async def echo(text: str) -> dict:
    return {"text": text}


@tool(description="Add two integers.")
async def add(a: int, b: int) -> dict:
    return {"sum": a + b}


def make_app(script):
    return App(tools=ToolRegistry([echo, add]), llm=ScriptedLLM(script))


# --- case loader ---------------------------------------------------------

def test_load_cases_from_yaml(tmp_path: Path):
    p = tmp_path / "cases.yaml"
    p.write_text(
        yaml.safe_dump(
            [
                {
                    "id": "c1",
                    "user_input": "say hi",
                    "expected_calls": [{"name": "echo", "args": {"text": "hi"}}],
                    "expected_text_includes": ["hi"],
                }
            ]
        ),
        encoding="utf-8",
    )
    cases = load_cases(p)
    assert len(cases) == 1
    assert cases[0].id == "c1"
    assert cases[0].expected_calls[0].name == "echo"


def test_match_args_supports_meta_keys():
    assert match_args({"x": {"__any__": True}}, {"x": 42}) == (True, "ok")
    assert match_args({"x": {"__regex__": r"^foo"}}, {"x": "foobar"})[0] is True
    assert match_args({"x": {"__regex__": r"^foo"}}, {"x": "bar"})[0] is False
    assert match_args({"x": {"__contains__": "ab"}}, {"x": "xaby"})[0] is True
    assert match_args({"x": 1}, {"x": 2})[0] is False
    assert match_args({"x": 1}, {})[0] is False


# --- runner --------------------------------------------------------------

async def test_runner_pass_basic():
    case = EvalCase(
        id="echo-basic",
        user_input="say hi",
        expected_calls=[ExpectedCall(name="echo", args={"text": "hi"})],
        expected_text_includes=["done"],
    )
    app = make_app(
        [
            ScriptedTurn(tool_calls=[ToolCall(id="1", name="echo", arguments={"text": "hi"})]),
            ScriptedTurn(text="all done."),
        ]
    )
    runner = EvalRunner(app)
    res = await runner.run(case)
    assert res.passed, res.reasons
    assert [o.name for o in res.observed_calls] == ["echo"]


async def test_runner_fail_missing_call():
    case = EvalCase(
        id="must-call-add",
        user_input="add 1 and 2",
        expected_calls=[ExpectedCall(name="add", args={"a": 1, "b": 2})],
    )
    app = make_app(
        [ScriptedTurn(text="I won't bother calling.")]
    )
    res = await EvalRunner(app).run(case)
    assert res.passed is False
    assert any("missing expected call" in r for r in res.reasons)


async def test_runner_fail_forbidden_call():
    case = EvalCase(
        id="must-not-echo",
        user_input="do nothing",
        forbidden_calls=["echo"],
    )
    app = make_app(
        [
            ScriptedTurn(tool_calls=[ToolCall(id="1", name="echo", arguments={"text": "oops"})]),
            ScriptedTurn(text="done."),
        ]
    )
    res = await EvalRunner(app).run(case)
    assert res.passed is False
    assert any("forbidden_call" in r for r in res.reasons)


async def test_runner_loose_order():
    case = EvalCase(
        id="loose",
        user_input="run both",
        expected_calls=[
            ExpectedCall(name="add", args={"a": 1, "b": 2}),
            ExpectedCall(name="echo", args={"text": "x"}),
        ],
        loose_order=True,
    )
    app = make_app(
        [
            ScriptedTurn(tool_calls=[ToolCall(id="1", name="echo", arguments={"text": "x"})]),
            ScriptedTurn(tool_calls=[ToolCall(id="2", name="add", arguments={"a": 1, "b": 2})]),
            ScriptedTurn(text="done."),
        ]
    )
    res = await EvalRunner(app).run(case)
    assert res.passed, res.reasons


async def test_runner_forbidden_text_fails():
    case = EvalCase(
        id="no-hallucination",
        user_input="don't say maybe",
        forbidden_text_includes=["maybe"],
    )
    app = make_app([ScriptedTurn(text="maybe later.")])
    res = await EvalRunner(app).run(case)
    assert res.passed is False


# --- scorecard ------------------------------------------------------------

async def test_scorecard_aggregates():
    cases = [
        EvalCase(id="ok1", user_input="x", expected_text_includes=["x"]),
        EvalCase(id="ok2", user_input="y", expected_text_includes=["y"]),
        EvalCase(id="fail1", user_input="z", forbidden_text_includes=["z"]),
    ]
    app = make_app(
        [
            ScriptedTurn(text="x found"),
            ScriptedTurn(text="y found"),
            ScriptedTurn(text="z forbidden"),
        ]
    )
    runner = EvalRunner(app)
    results = []
    for c in cases:
        # ScriptedLLM script is consumed turn-by-turn across runs;
        # re-seed by passing the per-case slice. Simplify: each turn = 1 script item.
        app.llm._script = [app.llm._script.pop(0)] if app.llm._script else []  # noqa: SLF001
        results.append(await runner.run(c))
    card = Scorecard(results)
    assert card.total == 3
    assert card.passed == 2
    assert "✅" in card.to_markdown()
    assert card.to_dict()["pass_rate"] == round(2 / 3, 4)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
