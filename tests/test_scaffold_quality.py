"""Unit tests for scaffold playability quality inspection and repair prompts."""

from __future__ import annotations

import json

from src.ham.builder_plan import Plan, Step
from src.ham.scaffold_quality import (
    ScaffoldQualityIssue,
    build_scaffold_repair_prompt,
    inspect_generated_scaffold_quality,
    maybe_repair_generated_scaffold,
    scaffold_quality_repair_enabled,
)


def _plan() -> Plan:
    return Plan(
        plan_id="pln_quality_test",
        workspace_id="ws_test",
        project_id="proj_test",
        user_message="Build a card battle game",
        steps=[Step(title="Scaffold", description="Create playable loop")],
        planner_confidence="high",
        metadata={"template_kind": "generic"},
    )


_STUB_REDUCER = """
const gameReducer = (state, action) => {
  switch (action.type) {
    case 'PLAY_CARD':
      // Logic to play card
      return { ...state };
    case 'END_TURN':
      return state;
    default:
      return state;
  }
};
"""

_IMPLEMENTED_REDUCER = """
function reducer(state, action) {
  switch (action.type) {
    case 'INCREMENT':
      return { ...state, count: state.count + 1 };
    default:
      return state;
  }
}
"""

_DISPATCH_MISMATCH_APP = """
import React, { useReducer } from 'react';
const reducer = (state, action) => {
  switch (action.type) {
    case 'ALLOCATE':
      return { ...state };
    default:
      return state;
  }
};
const App = () => {
  const [state, dispatch] = useReducer(reducer, { wood: 0 });
  return <button onClick={() => dispatch({ type: 'ALLOCATE' })}>Go</button>;
};
"""

_LOG_ONLY_APP = """
const playCard = (card) => {
  console.log('played', card);
};
"""

_STALE_WIN_APP = """
const App = () => {
  const [enemyHp, setEnemyHp] = useState(20);
  const checkWinCondition = () => {
    if (enemyHp <= 0) {
      setResult('win');
    }
  };
  const play = () => {
    setEnemyHp(prev => prev - 5);
    checkWinCondition();
  };
};
"""

_CLEAN_TYPING_APP = """
const App = () => {
  const [timer, setTimer] = useState(60);
  const handleInput = (value) => setInput(value);
  return <input onChange={(e) => handleInput(e.target.value)} />;
};
"""

_CLEAN_TYPING_MS_APP = """
const ROUND_MS = 60000;
const App = () => {
  const [timeLeft, setTimeLeft] = useState(ROUND_MS);
  return <div>{timeLeft}</div>;
};
"""

_CLEAN_TYPING_REDUCER_DURATION = """
export const reducer = (state, action) => {
  switch (action.type) {
    case 'TICK':
      if (state.elapsedSeconds < 60) {
        return { ...state, elapsedSeconds: state.elapsedSeconds + 1 };
      }
      return { ...state, isFinished: true };
    default:
      return state;
  }
};
"""

_ELAPSED_ONLY_TYPING_APP = """
const App = () => {
  const [elapsedTime, setElapsedTime] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => {
      setElapsedTime(prev => prev + 1);
      if (elapsedTime >= 59) setIsFinished(true);
    }, 1000);
  }, []);
};
"""

_NO_RESULT_CARD_APP = """
const Game = () => {
  const [enemyHp, setEnemyHp] = useState(20);
  const playCard = () => setEnemyHp(prev => prev - 5);
  return <button onClick={playCard}>Play</button>;
};
"""

_WITH_RESULT_CARD_APP = """
const Game = () => {
  const [enemyHp, setEnemyHp] = useState(20);
  const [result, setResult] = useState(null);
  const playCard = () => {
    const next = Math.max(enemyHp - 5, 0);
    setEnemyHp(next);
    if (next <= 0) setResult('win');
  };
  return result ? <div>Victory!</div> : <button onClick={playCard}>Play</button>;
};
"""


class TestInspectGeneratedScaffoldQuality:
    def test_detects_noop_primary_reducer_action(self):
        files = [("src/gameReducer.ts", _STUB_REDUCER)]
        issues = inspect_generated_scaffold_quality(files)
        codes = {i.code for i in issues}
        assert "noop_reducer_action" in codes
        assert any("PLAY_CARD" in i.message for i in issues)

    def test_detects_stub_placeholder_in_core_path(self):
        files = [("src/App.tsx", _STUB_REDUCER)]
        issues = inspect_generated_scaffold_quality(files)
        assert any(i.code == "stub_placeholder" for i in issues)

    def test_does_not_flag_default_reducer_fallback_alone(self):
        files = [("src/App.tsx", _IMPLEMENTED_REDUCER)]
        issues = inspect_generated_scaffold_quality(files)
        assert not any(i.code == "noop_reducer_action" for i in issues)

    def test_does_not_flag_implemented_reducer_cases(self):
        files = [("src/App.tsx", _IMPLEMENTED_REDUCER)]
        issues = inspect_generated_scaffold_quality(files)
        assert issues == []

    def test_detects_import_export_mismatch(self):
        files = [
            (
                "src/App.tsx",
                "import { Game } from './Game';\nexport default function App() { return <Game />; }",
            ),
            ("src/Game.tsx", "const Game = () => <div />;\nexport default Game;"),
        ]
        issues = inspect_generated_scaffold_quality(files)
        assert any(i.code == "import_export_mismatch" for i in issues)

    def test_detects_dispatch_reducer_mismatch(self):
        issues = inspect_generated_scaffold_quality([("src/App.tsx", _DISPATCH_MISMATCH_APP)])
        assert any(i.code == "dispatch_reducer_mismatch" for i in issues)

    def test_detects_log_only_primary_handler(self):
        issues = inspect_generated_scaffold_quality([("src/App.tsx", _LOG_ONLY_APP)])
        assert any(i.code == "empty_primary_handler" for i in issues)

    def test_detects_stale_state_win_check(self):
        issues = inspect_generated_scaffold_quality([("src/App.tsx", _STALE_WIN_APP)])
        assert any(i.code == "stale_state_win_check" for i in issues)

    def test_detects_timer_duration_mismatch_for_60s_prompt(self):
        plan = _plan()
        plan.user_message = "Build a typing game with a final score after 60 seconds."
        issues = inspect_generated_scaffold_quality(
            [("src/App.tsx", "const [timer, setTimer] = useState(0);")],
            plan=plan,
        )
        assert any(i.code == "timer_duration_mismatch" for i in issues)

    def test_detects_elapsed_only_timer_without_explicit_60(self):
        plan = _plan()
        plan.user_message = "Build a 60-second typing race with a final score."
        issues = inspect_generated_scaffold_quality(
            [("src/App.tsx", _ELAPSED_ONLY_TYPING_APP)],
            plan=plan,
        )
        assert any(i.code == "timer_duration_mismatch" for i in issues)

    def test_clean_typing_app_not_overflagged(self):
        plan = _plan()
        plan.user_message = "Build a typing game with a final score after 60 seconds."
        issues = inspect_generated_scaffold_quality(
            [("src/App.tsx", _CLEAN_TYPING_APP)],
            plan=plan,
        )
        assert not any(i.code == "timer_duration_mismatch" for i in issues)
        assert not any(i.code == "empty_primary_handler" for i in issues)

    def test_clean_typing_ms_duration_not_overflagged(self):
        plan = _plan()
        plan.user_message = "Build a typing game with a final score after 60 seconds."
        issues = inspect_generated_scaffold_quality(
            [("src/App.tsx", _CLEAN_TYPING_MS_APP)],
            plan=plan,
        )
        assert not any(i.code == "timer_duration_mismatch" for i in issues)

    def test_reducer_elapsed_less_than_60_not_overflagged(self):
        plan = _plan()
        plan.user_message = "Build a typing game with a final score after 60 seconds."
        issues = inspect_generated_scaffold_quality(
            [("src/typingReducer.ts", _CLEAN_TYPING_REDUCER_DURATION)],
            plan=plan,
        )
        assert not any(i.code == "timer_duration_mismatch" for i in issues)

    def test_detects_missing_result_state_for_win_prompt(self):
        plan = _plan()
        plan.user_message = (
            "Build a card battle game and wins by reducing the enemy health to zero."
        )
        issues = inspect_generated_scaffold_quality(
            [("src/components/Game.tsx", _NO_RESULT_CARD_APP)],
            plan=plan,
        )
        assert any(i.code == "missing_result_state" for i in issues)

    def test_win_prompt_with_result_state_not_overflagged(self):
        plan = _plan()
        plan.user_message = (
            "Build a card battle game and wins by reducing the enemy health to zero."
        )
        issues = inspect_generated_scaffold_quality(
            [("src/components/Game.tsx", _WITH_RESULT_CARD_APP)],
            plan=plan,
        )
        assert not any(i.code == "missing_result_state" for i in issues)


class TestBuildScaffoldRepairPrompt:
    def test_repair_prompt_includes_detected_issues_and_mutation_guidance(self):
        issues = [
            ScaffoldQualityIssue(
                code="noop_reducer_action",
                message="Reducer action 'PLAY_CARD' is a stub or no-op",
                path="src/gameReducer.ts",
            )
        ]
        messages = build_scaffold_repair_prompt(
            _plan(),
            [("src/gameReducer.ts", _STUB_REDUCER)],
            issues,
            base_system_prompt="BASE PROMPT",
        )
        assert messages[0]["role"] == "system"
        assert "repair mode" in messages[0]["content"].lower()
        assert "mutate state" in messages[0]["content"].lower()
        assert "stale-state" in messages[0]["content"].lower()
        assert "60 seconds" in messages[0]["content"].lower()
        assert "PLAY_CARD" in messages[1]["content"]
        assert "playability checks" in messages[1]["content"].lower()

    def test_repair_prompt_adds_timer_focus_when_timer_issue_present(self):
        issues = [
            ScaffoldQualityIssue(
                code="timer_duration_mismatch",
                message="Prompt requests a 60-second round",
                path="src/App.tsx",
            )
        ]
        messages = build_scaffold_repair_prompt(
            Plan(
                plan_id="pln_timer",
                workspace_id="ws",
                project_id="p",
                user_message="Build a typing game with a final score after 60 seconds.",
                steps=[Step(title="Scaffold", description="Create game")],
                planner_confidence="high",
            ),
            [("src/App.tsx", "const [elapsedTime, setElapsedTime] = useState(0);")],
            issues,
            base_system_prompt="BASE",
        )
        assert "Timer repair focus" in messages[0]["content"]
        assert "60000 ms" in messages[0]["content"]
        assert "final score" in messages[0]["content"].lower()

    def test_repair_prompt_adds_result_focus_when_result_issue_present(self):
        issues = [
            ScaffoldQualityIssue(
                code="missing_result_state",
                message="Prompt requires win/loss/final result",
                path="src/Game.tsx",
            )
        ]
        messages = build_scaffold_repair_prompt(
            Plan(
                plan_id="pln_result",
                workspace_id="ws",
                project_id="p",
                user_message="Wins by reducing the enemy health to zero.",
                steps=[Step(title="Scaffold", description="Create game")],
                planner_confidence="high",
            ),
            [("src/Game.tsx", _NO_RESULT_CARD_APP)],
            issues,
            base_system_prompt="BASE",
        )
        assert "Result-state repair focus" in messages[0]["content"]
        assert "restart" in messages[0]["content"].lower()


class TestMaybeRepairGeneratedScaffold:
    def test_skips_repair_when_no_issues(self):
        class _Result:
            file_changes = [("src/App.tsx", _IMPLEMENTED_REDUCER)]

        original = _Result()
        calls: list[int] = []

        def _complete_chat(*_a, **_k):
            calls.append(1)
            return "{}"

        out = maybe_repair_generated_scaffold(
            original,
            plan=_plan(),
            api_key="key",
            model="model",
            scaffold_timeout=30.0,
            base_system_prompt="BASE",
            parse_result=lambda _r: original,
            complete_chat=_complete_chat,
        )
        assert out is original
        assert calls == []

    def test_runs_single_repair_pass_when_issues_found(self):
        class _Result:
            file_changes = [("src/gameReducer.ts", _STUB_REDUCER)]

        class _Repaired:
            file_changes = [("src/gameReducer.ts", _IMPLEMENTED_REDUCER)]

        calls: list[list[dict]] = []

        def _complete_chat(messages, **_k):
            calls.append(messages)
            return json.dumps(
                {
                    "file_changes": [{"path": "src/App.tsx", "content": "ok"}],
                    "assertions": ["works"],
                }
            )

        def _parse(raw):
            return _Repaired()

        out = maybe_repair_generated_scaffold(
            _Result(),
            plan=_plan(),
            api_key="key",
            model="model",
            scaffold_timeout=30.0,
            base_system_prompt="BASE",
            parse_result=_parse,
            complete_chat=_complete_chat,
        )
        assert isinstance(out, _Repaired)
        assert len(calls) == 1
        assert "repair mode" in calls[0][0]["content"].lower()

    def test_logs_remaining_issues_after_repair(self, caplog):
        import logging

        class _Result:
            file_changes = [("src/App.tsx", _NO_RESULT_CARD_APP)]

        class _Repaired:
            file_changes = [("src/components/Game.tsx", _NO_RESULT_CARD_APP)]

        plan = _plan()
        plan.user_message = "Wins by reducing the enemy health to zero."

        caplog.set_level(logging.WARNING, logger="src.ham.scaffold_quality")

        maybe_repair_generated_scaffold(
            _Result(),
            plan=plan,
            api_key="key",
            model="model",
            scaffold_timeout=30.0,
            base_system_prompt="BASE",
            parse_result=lambda _r: _Repaired(),
            complete_chat=lambda *_a, **_k: "{}",
        )
        assert any("remain after repair" in record.message for record in caplog.records)

    def test_repair_disabled_via_env(self):
        class _Result:
            file_changes = [("src/gameReducer.ts", _STUB_REDUCER)]

        original = _Result()
        calls: list[int] = []

        def _complete_chat(*_a, **_k):
            calls.append(1)
            return "{}"

        out = maybe_repair_generated_scaffold(
            original,
            plan=_plan(),
            api_key="key",
            model="model",
            scaffold_timeout=30.0,
            base_system_prompt="BASE",
            parse_result=lambda _r: original,
            complete_chat=_complete_chat,
            env={"HAM_SCAFFOLD_QUALITY_REPAIR": "false"},
        )
        assert out is original
        assert calls == []
        assert scaffold_quality_repair_enabled(env={"HAM_SCAFFOLD_QUALITY_REPAIR": "false"}) is False


class TestGenerateScaffoldQualityRepairIntegration:
    def test_generate_scaffold_triggers_one_repair_llm_call(self, monkeypatch):
        from src.ham.builder_llm_scaffold import ScaffoldResult, generate_scaffold

        stub_json = json.dumps(
            {
                "file_changes": [
                    {"path": "src/reducer.ts", "content": _STUB_REDUCER},
                    {"path": "package.json", "content": "{}"},
                ],
                "assertions": ["renders"],
            }
        )
        fixed_json = json.dumps(
            {
                "file_changes": [
                    {"path": "src/App.tsx", "content": _IMPLEMENTED_REDUCER},
                ],
                "assertions": ["renders"],
            }
        )
        calls: list[str] = []

        def _complete_chat(messages, **_k):
            calls.append(messages[0]["content"])
            return fixed_json if len(calls) > 1 else stub_json

        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test",
        )
        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.complete_chat_messages_openrouter",
            _complete_chat,
        )
        result = generate_scaffold(_plan(), project_id="p", workspace_id="w")
        assert len(calls) == 2
        assert "repair mode" in calls[1].lower()
        assert isinstance(result, ScaffoldResult)
        assert result.file_changes[0][0] == "src/App.tsx"
