"""Eval framework — Case + Runner + ScriptedLLM + Scorecard.

This is the agent-process-management layer. It lets you:
  - Pin desired behavior as Cases (markdown-frontmatter or YAML)
  - Replay them through any agentkit App, with either:
      * ScriptedLLM (deterministic, no API key, runs in CI)
      * the real LLM (slower, validates the actual model behavior)
  - Aggregate pass/fail into a Scorecard with markdown + JSON output
"""

from agentkit.eval.case import EvalCase, ExpectedCall, MatcherDict, load_cases
from agentkit.eval.runner import CaseResult, EvalRunner
from agentkit.eval.scorecard import Scorecard
from agentkit.eval.scripted_llm import ScriptedLLM, ScriptedTurn

__all__ = [
    "CaseResult",
    "EvalCase",
    "EvalRunner",
    "ExpectedCall",
    "MatcherDict",
    "Scorecard",
    "ScriptedLLM",
    "ScriptedTurn",
    "load_cases",
]
