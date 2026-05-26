"""Unit tests for scaffold playability quality inspection and repair prompts."""

from __future__ import annotations

import json

from src.ham.builder_plan import Plan, Step
from src.ham.scaffold_quality import (
    ScaffoldQualityIssue,
    _merge_repair_file_changes,
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

_RHYTHM_GATE_PROMPT = (
    "Build a browser rhythm tap game where beat cues appear in sequence, the player "
    "presses space at the right time, earns perfect/good/miss scores based on timing "
    "accuracy, builds a combo streak, sees a final score, and can play again."
)

_RHYTHM_WITH_RESULT_APP = """
const RhythmGame = () => {
  const [gameState, setGameState] = useState('idle');
  const [finalScore, setFinalScore] = useState(0);
  const finishRound = (nextScore) => {
    setFinalScore(nextScore);
    setGameState('result');
  };
  const restartGame = () => setGameState('idle');
  return (
    <div>
      {gameState === 'result' && <p>Final Score: {finalScore}</p>}
      <button onClick={restartGame}>Play Again</button>
    </div>
  );
};
"""

_RHYTHM_NO_RESULT_APP = """
const RhythmGame = () => {
  const [score, setScore] = useState(0);
  return <div>Score: {score}</div>;
};
"""

_RHYTHM_MISS_STREAK_ONLY_APP = """
const handleTap = () => {
  if (offset <= timingWindows.perfect) {
    setScore((prev) => prev + 100);
    setStreak((prev) => prev + 1);
  } else if (offset <= timingWindows.good) {
    setScore((prev) => prev + 50);
    setStreak((prev) => prev + 1);
  } else {
    setStreak(0);
  }
};
"""

_RHYTHM_MISS_WITH_FEEDBACK_APP = """
const [missCount, setMissCount] = useState(0);
const [lastJudgment, setLastJudgment] = useState('');
const handleTap = () => {
  if (offset <= timingWindows.perfect) {
    setScore((prev) => prev + 100);
  } else if (offset <= timingWindows.good) {
    setScore((prev) => prev + 50);
  } else {
    setMissCount((prev) => prev + 1);
    setStreak(0);
    setLastJudgment('miss');
  }
};
return missCount > 0 ? <p>Misses: {missCount}</p> : null;
"""

_RHYTHM_STALE_FINAL_SCORE_APP = """
const finishRound = () => {
  setGameState('result');
  setFinalScore(score);
};
"""

_CARD_DECK_PROMPT = (
    "Build a browser card battle game where the player draws a hand from a shuffled deck, "
    "plays one card per turn, resolves card effects against a simple enemy, uses a discard pile, "
    "and wins by reducing the enemy health to zero."
)

_EMPTY_SHUFFLED_DECK_APP = """
const shuffledDeck = () => { return []; };
const drawInitialHand = () => { return []; };
const reducer = (state, action) => state;
"""

_SEEDED_DECK_APP = """
const CARDS = [{ id: 1, name: 'Strike', power: 5 }];
const shuffledDeck = () => [...CARDS].sort(() => Math.random() - 0.5);
const reducer = (state, action) => {
  switch (action.type) {
    case 'START_GAME':
      return { ...state, deck: shuffledDeck(), hand: shuffledDeck().slice(0, 3) };
    default:
      return state;
  }
};
"""

_UNWIRED_VICTORY_GAME = """
const reducer = (state, action) => {
  switch (action.type) {
    case 'PLAY_CARD':
      return { ...state, enemyHp: state.enemyHp - action.payload.power, discardPile: [...state.discardPile, action.payload] };
    case 'END_GAME':
      return { ...state, gameEnded: true };
    default:
      return state;
  }
};
const Game = () => {
  const [state, dispatch] = useReducer(reducer, { enemyHp: 20, discardPile: [], gameEnded: false });
  return (
    <>
      <Opponent enemyHp={state.enemyHp} />
      {state.gameEnded && <ResultsPanel enemyHp={state.enemyHp} />}
    </>
  );
};
"""

_WIRED_VICTORY_GAME = """
const reducer = (state, action) => {
  switch (action.type) {
    case 'PLAY_CARD': {
      const nextHp = state.enemyHp - action.payload.power;
      const next = { ...state, enemyHp: nextHp, discardPile: [...state.discardPile, action.payload] };
      return nextHp <= 0 ? { ...next, gameEnded: true } : next;
    }
    case 'END_GAME':
      return { ...state, gameEnded: true };
    default:
      return state;
  }
};
"""

_IMPLEMENTED_DRAW_CARD = """
const reducer = (state, action) => {
  switch (action.type) {
    case 'DRAW_CARD':
      if (state.deck.length === 0) return state;
      const cardToDraw = state.deck[0];
      return {
        ...state,
        deck: state.deck.slice(1),
        hand: [...state.hand, cardToDraw]
      };
    default:
      return state;
  }
};
"""

_NOOP_DRAW_CARD = """
const reducer = (state, action) => {
  switch (action.type) {
    case 'DRAW_CARD':
      return state;
    default:
      return state;
  }
};
"""

_IGNORED_SEED_PAYLOAD_APP = """
const initialState = { playerHealth: 20, enemyHealth: 20, deck: [], hand: [], discard: [] };
const reducer = (state, action) => {
  switch (action.type) {
    case 'NEW_GAME':
      return initialState;
    case 'PLAY_CARD':
      return { ...state, enemyHealth: state.enemyHealth - action.card.power };
    default:
      return state;
  }
};
export const App = () => {
  const [state, dispatch] = useReducer(reducer, initialState);
  useEffect(() => {
    const shuffledDeck = [...Array(10).keys()].map(i => ({ id: i, power: 3 }));
    dispatch({ type: 'NEW_GAME', deck: shuffledDeck });
  }, []);
};
"""

_APPLIED_SEED_PAYLOAD_APP = """
const initialState = { deck: [], hand: [], discard: [], enemyHealth: 20 };
const reducer = (state, action) => {
  switch (action.type) {
    case 'NEW_GAME':
      return {
        ...initialState,
        deck: action.payload.deck,
        hand: action.payload.hand || action.payload.deck.slice(0, 3),
      };
    default:
      return state;
  }
};
"""

_DECK_BUILDER_GATE_PROMPT = (
    "Build a browser deck-building card game where the player starts with a small deck, "
    "draws a hand, plays cards against a simple enemy, discards played cards, chooses one "
    "card reward after each win, adds it to the deck, and tries to complete a short run."
)

_INITIALIZED_DECK_APP = """
const initialState = { deck: [], hand: [], discard: [] };
const initialDeck = () => [{ id: '1', name: 'Attack' }, { id: '2', name: 'Defend' }];
const drawHand = () => [initialDeck()[0]];
const reducer = (state, action) => {
  switch (action.type) {
    case 'INITIALIZE':
      return { ...state, deck: initialDeck(), hand: drawHand() };
    default:
      return state;
  }
};
export const App = () => {
  const [state, dispatch] = useReducer(reducer, initialState);
  useEffect(() => { dispatch({ type: 'INITIALIZE' }); }, []);
};
"""

_EMPTY_REWARD_POOL_APP = """
const rewards = [];
const reducer = (state, action) => state;
const Game = () => state.phase === 'reward' ? <RewardChoicePanel rewards={rewards} /> : null;
"""

_POPULATED_REWARD_POOL_APP = """
const rewards = [{ id: 'r1', name: 'Bolt' }, { id: 'r2', name: 'Shield' }];
const reducer = (state, action) => {
  switch (action.type) {
    case 'SELECT_REWARD':
      return { ...state, deck: [...state.deck, action.payload], phase: 'encounter' };
    default:
      return state;
  }
};
"""

_REWARD_NOT_WIRED_APP = """
const reducer = (state, action) => {
  switch (action.type) {
    case 'SELECT_REWARD':
      return { ...state, phase: 'encounter' };
    default:
      return state;
  }
};
"""

_DISCARD_NOT_WIRED_APP = """
const reducer = (state, action) => {
  switch (action.type) {
    case 'PLAY_CARD':
      return { ...state, hand: state.hand.filter(c => c.id !== action.payload), enemyHp: state.enemyHp - 1 };
    default:
      return state;
  }
};
const initialState = { deck: [{ id: 1 }], hand: [{ id: 1 }], discardPile: [], enemyHp: 10 };
"""

_DISCARD_WIRED_APP = """
const reducer = (state, action) => {
  switch (action.type) {
    case 'PLAY_CARD': {
      const card = state.hand.find(c => c.id === action.payload);
      return {
        ...state,
        hand: state.hand.filter(c => c.id !== action.payload),
        discardPile: [...state.discardPile, card],
        enemyHp: state.enemyHp - 1,
      };
    }
    default:
      return state;
  }
};
"""

_DECK_BUILDER_NO_RESTART_APP = """
const reducer = (state, action) => state;
const Game = () => <div>Encounter {state.encounter}</div>;
"""

_DECK_BUILDER_WITH_RESTART_APP = """
const Game = () => (
  <>
    <ResultsPanel />
    <button onClick={playAgain}>Play Again</button>
  </>
);
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

    def test_rhythm_result_phase_not_flagged_as_missing_result_state(self):
        plan = _plan()
        plan.user_message = _RHYTHM_GATE_PROMPT
        issues = inspect_generated_scaffold_quality(
            [("src/components/RhythmGame.tsx", _RHYTHM_WITH_RESULT_APP)],
            plan=plan,
        )
        assert not any(i.code == "missing_result_state" for i in issues)

    def test_rhythm_prompt_without_result_is_flagged(self):
        plan = _plan()
        plan.user_message = _RHYTHM_GATE_PROMPT
        issues = inspect_generated_scaffold_quality(
            [("src/components/RhythmGame.tsx", _RHYTHM_NO_RESULT_APP)],
            plan=plan,
        )
        assert any(i.code == "missing_result_state" for i in issues)

    def test_rhythm_miss_streak_only_is_flagged(self):
        plan = _plan()
        plan.user_message = _RHYTHM_GATE_PROMPT
        issues = inspect_generated_scaffold_quality(
            [("src/components/RhythmGame.tsx", _RHYTHM_MISS_STREAK_ONLY_APP)],
            plan=plan,
        )
        assert any(i.code == "rhythm_miss_feedback_weak" for i in issues)

    def test_rhythm_miss_with_feedback_not_overflagged(self):
        plan = _plan()
        plan.user_message = _RHYTHM_GATE_PROMPT
        issues = inspect_generated_scaffold_quality(
            [("src/components/RhythmGame.tsx", _RHYTHM_MISS_WITH_FEEDBACK_APP)],
            plan=plan,
        )
        assert not any(i.code == "rhythm_miss_feedback_weak" for i in issues)

    def test_rhythm_stale_final_score_is_flagged(self):
        plan = _plan()
        plan.user_message = _RHYTHM_GATE_PROMPT
        issues = inspect_generated_scaffold_quality(
            [("src/components/RhythmGame.tsx", _RHYTHM_STALE_FINAL_SCORE_APP)],
            plan=plan,
        )
        assert any(i.code == "rhythm_result_state_weak" for i in issues)

    def test_detects_empty_shuffled_deck_for_card_prompt(self):
        plan = _plan()
        plan.user_message = _CARD_DECK_PROMPT
        issues = inspect_generated_scaffold_quality(
            [("src/components/Game.tsx", _EMPTY_SHUFFLED_DECK_APP)],
            plan=plan,
        )
        assert any(i.code == "empty_deck_seed" for i in issues)

    def test_seeded_deck_not_overflagged(self):
        plan = _plan()
        plan.user_message = _CARD_DECK_PROMPT
        issues = inspect_generated_scaffold_quality(
            [("src/components/Game.tsx", _SEEDED_DECK_APP)],
            plan=plan,
        )
        assert not any(i.code == "empty_deck_seed" for i in issues)

    def test_detects_missing_victory_wiring_when_end_game_never_fires(self):
        plan = _plan()
        plan.user_message = _CARD_DECK_PROMPT
        issues = inspect_generated_scaffold_quality(
            [("src/components/Game.tsx", _UNWIRED_VICTORY_GAME)],
            plan=plan,
        )
        assert any(i.code == "missing_victory_wiring" for i in issues)

    def test_wired_victory_on_enemy_hp_not_overflagged(self):
        plan = _plan()
        plan.user_message = _CARD_DECK_PROMPT
        issues = inspect_generated_scaffold_quality(
            [("src/components/Game.tsx", _WIRED_VICTORY_GAME)],
            plan=plan,
        )
        assert not any(i.code == "missing_victory_wiring" for i in issues)

    def test_implemented_draw_card_not_flagged_as_noop(self):
        issues = inspect_generated_scaffold_quality([("src/Game.tsx", _IMPLEMENTED_DRAW_CARD)])
        assert not any(
            i.code == "noop_reducer_action" and "DRAW_CARD" in i.message for i in issues
        )

    def test_true_noop_draw_card_still_flagged(self):
        issues = inspect_generated_scaffold_quality([("src/Game.tsx", _NOOP_DRAW_CARD)])
        assert any(i.code == "noop_reducer_action" and "DRAW_CARD" in i.message for i in issues)

    def test_detects_ignored_seed_payload_for_new_game(self):
        plan = _plan()
        plan.user_message = _CARD_DECK_PROMPT
        issues = inspect_generated_scaffold_quality(
            [("src/App.tsx", _IGNORED_SEED_PAYLOAD_APP)],
            plan=plan,
        )
        assert any(i.code == "ignored_seed_payload" for i in issues)

    def test_applied_seed_payload_not_overflagged(self):
        plan = _plan()
        plan.user_message = _CARD_DECK_PROMPT
        issues = inspect_generated_scaffold_quality(
            [("src/App.tsx", _APPLIED_SEED_PAYLOAD_APP)],
            plan=plan,
        )
        assert not any(i.code == "ignored_seed_payload" for i in issues)

    def test_populated_seed_with_empty_new_game_reducer_flagged(self):
        plan = _plan()
        plan.user_message = _CARD_DECK_PROMPT
        issues = inspect_generated_scaffold_quality(
            [
                (
                    "src/App.tsx",
                    """
const CARDS = [{ id: 1, name: 'Strike', power: 5 }];
const initialState = { deck: [], hand: [] };
const reducer = (state, action) => {
  switch (action.type) {
    case 'NEW_GAME': return initialState;
    default: return state;
  }
};
""",
                )
            ],
            plan=plan,
        )
        assert any(
            i.code in {"ignored_seed_payload", "empty_deck_seed"} for i in issues
        )

    def test_initialized_deck_on_mount_not_flagged_as_empty_seed(self):
        plan = _plan()
        plan.user_message = _DECK_BUILDER_GATE_PROMPT
        issues = inspect_generated_scaffold_quality(
            [("src/App.tsx", _INITIALIZED_DECK_APP)],
            plan=plan,
        )
        assert not any(i.code == "empty_deck_seed" for i in issues)

    def test_draw_pile_seeded_initial_state_not_flagged_as_empty_seed(self):
        plan = _plan()
        plan.user_message = _DECK_BUILDER_GATE_PROMPT
        app = """
export const initialState = {
  drawPile: [{ id: 1, name: 'Attack', damage: 5 }],
  hand: [],
  discardPile: [],
};
"""
        issues = inspect_generated_scaffold_quality(
            [("src/reducers/gameReducer.ts", app)],
            plan=plan,
        )
        assert not any(i.code == "empty_deck_seed" for i in issues)

    def test_empty_reward_pool_flagged_for_deck_builder_prompt(self):
        plan = _plan()
        plan.user_message = _DECK_BUILDER_GATE_PROMPT
        issues = inspect_generated_scaffold_quality(
            [("src/components/Game.tsx", _EMPTY_REWARD_POOL_APP)],
            plan=plan,
        )
        assert any(i.code == "empty_reward_pool" for i in issues)

    def test_populated_reward_pool_not_overflagged(self):
        plan = _plan()
        plan.user_message = _DECK_BUILDER_GATE_PROMPT
        issues = inspect_generated_scaffold_quality(
            [("src/state/gameReducer.ts", _POPULATED_REWARD_POOL_APP)],
            plan=plan,
        )
        assert not any(i.code == "empty_reward_pool" for i in issues)

    def test_reward_choice_not_wired_to_deck_is_flagged(self):
        plan = _plan()
        plan.user_message = _DECK_BUILDER_GATE_PROMPT
        issues = inspect_generated_scaffold_quality(
            [("src/state/gameReducer.ts", _REWARD_NOT_WIRED_APP)],
            plan=plan,
        )
        assert any(i.code == "reward_choice_not_wired" for i in issues)

    def test_reward_choice_appending_to_deck_not_overflagged(self):
        plan = _plan()
        plan.user_message = _DECK_BUILDER_GATE_PROMPT
        issues = inspect_generated_scaffold_quality(
            [("src/state/gameReducer.ts", _POPULATED_REWARD_POOL_APP)],
            plan=plan,
        )
        assert not any(i.code == "reward_choice_not_wired" for i in issues)

    def test_discard_pile_not_wired_is_flagged(self):
        plan = _plan()
        plan.user_message = _DECK_BUILDER_GATE_PROMPT
        issues = inspect_generated_scaffold_quality(
            [("src/state/gameReducer.ts", _DISCARD_NOT_WIRED_APP)],
            plan=plan,
        )
        assert any(i.code == "discard_not_wired" for i in issues)

    def test_discard_pile_append_not_overflagged(self):
        plan = _plan()
        plan.user_message = _DECK_BUILDER_GATE_PROMPT
        issues = inspect_generated_scaffold_quality(
            [("src/state/gameReducer.ts", _DISCARD_WIRED_APP)],
            plan=plan,
        )
        assert not any(i.code == "discard_not_wired" for i in issues)

    def test_missing_restart_flagged_for_deck_builder_run_prompt(self):
        plan = _plan()
        plan.user_message = _DECK_BUILDER_GATE_PROMPT
        issues = inspect_generated_scaffold_quality(
            [("src/components/Game.tsx", _DECK_BUILDER_NO_RESTART_APP)],
            plan=plan,
        )
        assert any(i.code == "missing_restart_action" for i in issues)

    def test_restart_present_not_overflagged_for_deck_builder(self):
        plan = _plan()
        plan.user_message = _DECK_BUILDER_GATE_PROMPT
        issues = inspect_generated_scaffold_quality(
            [("src/components/Game.tsx", _DECK_BUILDER_WITH_RESTART_APP)],
            plan=plan,
        )
        assert not any(i.code == "missing_restart_action" for i in issues)


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

    def test_repair_prompt_adds_rhythm_focus_when_rhythm_issue_present(self):
        issues = [
            ScaffoldQualityIssue(
                code="rhythm_miss_feedback_weak",
                message="Rhythm miss handling only resets streak",
                path="src/components/RhythmGame.tsx",
            )
        ]
        messages = build_scaffold_repair_prompt(
            Plan(
                plan_id="pln_rhythm",
                workspace_id="ws",
                project_id="p",
                user_message=_RHYTHM_GATE_PROMPT,
                steps=[Step(title="Scaffold", description="Create game")],
                planner_confidence="high",
            ),
            [("src/components/RhythmGame.tsx", _RHYTHM_MISS_STREAK_ONLY_APP)],
            issues,
            base_system_prompt="BASE",
        )
        assert "Rhythm/timing repair focus" in messages[0]["content"]
        assert "miss counters" in messages[0]["content"].lower()
        assert "stale closure" in messages[0]["content"].lower()

    def test_repair_prompt_adds_card_deck_focus_when_deck_issue_present(self):
        issues = [
            ScaffoldQualityIssue(
                code="empty_deck_seed",
                message="deck seed empty",
                path="src/Game.tsx",
            )
        ]
        plan = _plan()
        plan.user_message = _CARD_DECK_PROMPT
        messages = build_scaffold_repair_prompt(
            plan,
            [("src/Game.tsx", _EMPTY_SHUFFLED_DECK_APP)],
            issues,
            base_system_prompt="BASE",
        )
        assert "Card-deck repair focus" in messages[0]["content"]
        assert "shuffled deck" in messages[0]["content"].lower()
        assert "enemy HP reaches zero" in messages[0]["content"]

    def test_repair_prompt_adds_seed_payload_guidance(self):
        issues = [
            ScaffoldQualityIssue(
                code="ignored_seed_payload",
                message="Reducer ignores seeded deck payload",
                path="src/App.tsx",
            )
        ]
        plan = _plan()
        plan.user_message = _CARD_DECK_PROMPT
        messages = build_scaffold_repair_prompt(
            plan,
            [("src/App.tsx", _IGNORED_SEED_PAYLOAD_APP)],
            issues,
            base_system_prompt="BASE",
        )
        body = messages[0]["content"]
        assert "action.payload" in body
        assert "NEW_GAME/RESET/START" in body
        assert "non-empty at game start" in body.lower()

    def test_repair_prompt_adds_deck_builder_focus_when_deck_builder_issue_present(self):
        issues = [
            ScaffoldQualityIssue(
                code="empty_reward_pool",
                message="reward pool empty",
                path="src/state/gameReducer.ts",
            ),
            ScaffoldQualityIssue(
                code="discard_not_wired",
                message="discard not wired",
                path="src/state/gameReducer.ts",
            ),
        ]
        plan = _plan()
        plan.user_message = _DECK_BUILDER_GATE_PROMPT
        messages = build_scaffold_repair_prompt(
            plan,
            [("src/state/gameReducer.ts", _EMPTY_REWARD_POOL_APP)],
            issues,
            base_system_prompt="BASE",
        )
        body = messages[0]["content"]
        assert "Deck-builder repair focus" in body
        assert "non-empty reward pool" in body.lower()
        assert "push card to discard" in body.lower()
        assert "restart/new-run/play-again" in body.lower()


class TestMergeRepairFileChanges:
    def test_preserves_original_paths_when_repair_returns_subset(self):
        original = [
            ("src/reducer.ts", "ORIG_REDUCER"),
            ("package.json", "{}"),
        ]
        repaired = [("src/App.tsx", "NEW_APP")]
        merged = _merge_repair_file_changes(original, repaired)
        assert merged == [
            ("src/reducer.ts", "ORIG_REDUCER"),
            ("package.json", "{}"),
            ("src/App.tsx", "NEW_APP"),
        ]

    def test_overlays_content_for_paths_present_in_both(self):
        original = [("src/App.tsx", "OLD"), ("package.json", "{}")]
        repaired = [("src/App.tsx", "NEW")]
        assert _merge_repair_file_changes(original, repaired) == [
            ("src/App.tsx", "NEW"),
            ("package.json", "{}"),
        ]


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
            file_changes = [("src/App.tsx", _IMPLEMENTED_REDUCER)]

        calls: list[list[dict]] = []

        def _complete_chat(messages, **_k):
            calls.append(messages)
            return json.dumps(
                {
                    "file_changes": [{"path": "src/App.tsx", "content": "ignored"}],
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
        paths = [p for p, _ in out.file_changes]
        assert paths == ["src/gameReducer.ts", "src/App.tsx"]
        assert out.file_changes[0][1] == _STUB_REDUCER
        assert out.file_changes[1][1] == _IMPLEMENTED_REDUCER

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
        paths = [p for p, _ in result.file_changes]
        assert paths == ["src/reducer.ts", "package.json", "src/App.tsx"]
        assert result.file_changes[0][1] == _STUB_REDUCER
        assert result.file_changes[1][1] == "{}"
        assert result.file_changes[2][1] == _IMPLEMENTED_REDUCER
