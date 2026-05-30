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


_TACTICS_GATE_PROMPT = (
    "Build a browser turn-based tactics game on a small 5x5 grid where the player "
    "selects units, moves them within range, attacks enemy units, resolves a simple "
    "enemy turn, wins by defeating all enemies, loses if all player units are defeated, "
    "and can restart the battle."
)

_TACTICS_SHELL_REDUCER = """
export const initialState = { grid: [], units: [], events: [], result: null };
export const gameReducer = (state, action) => {
  switch (action.type) {
    case 'INIT_GAME': {
      const units = [
        { id: 1, hp: 100, position: { x: 0, y: 0 }, isPlayer: true },
        { id: 2, hp: 100, position: { x: 1, y: 0 }, isPlayer: true }
      ];
      return { ...state, units, events: ['Game Initialized'], result: null };
    }
    case 'MOVE_UNIT': {
      const { unitId, to } = action.payload;
      const newUnits = state.units.map(u => u.id === unitId ? { ...u, position: to } : u);
      return { ...state, units: newUnits, events: ['Unit Moved'] };
    }
    case 'ATTACK_UNIT': {
      const { targetId } = action.payload;
      const newUnits = state.units.map(u =>
        u.id === targetId ? { ...u, hp: u.hp - 20 } : u
      );
      return { ...state, units: newUnits, events: ['Unit Attacked'] };
    }
    case 'END_TURN':
      return { ...state, events: ['Turn Ended'], result: null };
    case 'RESTART_GAME':
      return initialState;
    default:
      return state;
  }
};
"""

_TACTICS_SHELL_GRID = """
const Board = ({ grid, units, dispatch }) => (
  <div className="grid grid-cols-5 gap-1">
    {grid.map((row, rowIndex) => row.map((cell, colIndex) => (
      <div key={`${rowIndex}-${colIndex}`} className="w-12 h-12 bg-gray-300">
        {units.find(u => u.position.x === colIndex && u.position.y === rowIndex)?.id}
      </div>
    )))}
  </div>
);
export default Board;
"""

_TACTICS_SHELL_GAME = """
import React, { useReducer } from 'react';
import { initialState, gameReducer } from './gameReducer';
import Board from './components/TacticsGridBoard';
const Game = () => {
  const [state, dispatch] = useReducer(gameReducer, initialState);
  return <Board grid={state.grid} units={state.units} dispatch={dispatch} />;
};
export default Game;
"""

_TACTICS_MOUNTED_INIT_REDUCER = """
export const initialState = { grid: [], units: [], events: [], result: null };
export const gameReducer = (state, action) => {
  switch (action.type) {
    case 'INIT_GAME': {
      const units = [
        { id: 1, hp: 100, position: { x: 0, y: 0 }, isPlayer: true },
        { id: 2, hp: 80, position: { x: 4, y: 4 }, isPlayer: false },
      ];
      return { ...state, units, events: ['Game Initialized'], result: null };
    }
    default:
      return state;
  }
};
"""

_TACTICS_MOUNTED_INIT_GAME = """
import React, { useReducer, useEffect } from 'react';
import { initialState, gameReducer } from './gameReducer';
export const App = () => {
  const [state, dispatch] = useReducer(gameReducer, initialState);
  useEffect(() => { dispatch({ type: 'INIT_GAME' }); }, []);
  return <div>{state.units.length}</div>;
};
"""

_TACTICS_SEEDED_INITIAL_STATE = """
export const initialState = {
  units: [
    { id: 1, hp: 100, position: { x: 0, y: 0 }, isPlayer: true },
    { id: 2, hp: 80, position: { x: 4, y: 4 }, isPlayer: false },
  ],
  selectedUnitId: null,
  phase: 'player',
  result: null,
};
export const gameReducer = (state, action) => state;
"""

_TACTICS_UNWIRED_ACTIONS = """
const reducer = (state, action) => {
  switch (action.type) {
    case 'SELECT_UNIT':
      return { ...state, selectedUnitId: action.payload };
    case 'MOVE_UNIT':
      return { ...state, units: state.units.map(u =>
        u.id === action.payload.unitId ? { ...u, position: action.payload.to } : u) };
    case 'ATTACK_UNIT':
      return { ...state, units: state.units.map(u =>
        u.id === action.payload.targetId ? { ...u, hp: u.hp - 10 } : u) };
    default:
      return state;
  }
};
const ActionBar = () => <button>End Turn</button>;
"""

_TACTICS_WIRED_APP = """
const moveRange = 2;
const attackRange = 1;
const reducer = (state, action) => {
  switch (action.type) {
    case 'INIT_GAME':
      return {
        ...state,
        units: [
          { id: 1, hp: 100, position: { x: 0, y: 0 }, isPlayer: true },
          { id: 2, hp: 80, position: { x: 4, y: 4 }, isPlayer: false },
        ],
        phase: 'player',
        result: null,
      };
    case 'SELECT_UNIT':
      return { ...state, selectedUnitId: action.payload };
    case 'MOVE_UNIT': {
      const unit = state.units.find(u => u.id === action.payload.unitId);
      const dist = Math.abs(unit.position.x - action.payload.to.x)
        + Math.abs(unit.position.y - action.payload.to.y);
      if (dist > moveRange) return state;
      return { ...state, units: state.units.map(u =>
        u.id === action.payload.unitId ? { ...u, position: action.payload.to } : u) };
    }
    case 'ATTACK_UNIT': {
      const attacker = state.units.find(u => u.id === action.payload.attackerId);
      const target = state.units.find(u => u.id === action.payload.targetId);
      const dist = Math.abs(attacker.position.x - target.position.x)
        + Math.abs(attacker.position.y - target.position.y);
      if (dist > attackRange) return state;
      const units = state.units.map(u =>
        u.id === action.payload.targetId ? { ...u, hp: u.hp - 15 } : u);
      const enemiesAlive = units.some(u => !u.isPlayer && u.hp > 0);
      const playersAlive = units.some(u => u.isPlayer && u.hp > 0);
      let result = state.result;
      if (!enemiesAlive) result = 'You Won';
      if (!playersAlive) result = 'You Lose';
      return { ...state, units, result };
    }
    case 'END_TURN': {
      const enemy = state.units.find(u => !u.isPlayer && u.hp > 0);
      const player = state.units.find(u => u.isPlayer && u.hp > 0);
      const units = state.units.map(u =>
        u.id === enemy.id ? { ...u, hp: u.hp - 5 } : u
      );
      return { ...state, units, phase: 'player' };
    }
    case 'RESTART_GAME':
      return reducer(state, { type: 'INIT_GAME' });
    default:
      return state;
  }
};
const Grid = ({ dispatch }) => (
  <div className="grid grid-cols-5" onClick={() => dispatch({ type: 'SELECT_UNIT', payload: 1 })}>
    <button onClick={() => dispatch({ type: 'MOVE_UNIT', payload: { unitId: 1, to: { x: 1, y: 0 } } })}>Move</button>
    <button onClick={() => dispatch({ type: 'ATTACK_UNIT', payload: { attackerId: 1, targetId: 2 } })}>Attack</button>
    <button onClick={() => dispatch({ type: 'END_TURN' })}>End Turn</button>
    <button onClick={() => dispatch({ type: 'RESTART_GAME' })}>Restart Battle</button>
  </div>
);
const TacticsResultsPanel = ({ result }) => result ? <div>{result}</div> : null;
export const App = () => {
  const [state, dispatch] = useReducer(reducer, { units: [], phase: 'player', result: null });
  useEffect(() => { dispatch({ type: 'INIT_GAME' }); }, []);
  return (<><Grid dispatch={dispatch} /><TacticsResultsPanel result={state.result} /></>);
};
"""

_TACTICS_RESTART_EMPTY = """
export const initialState = { units: [], result: null };
export const gameReducer = (state, action) => {
  switch (action.type) {
    case 'RESTART_GAME':
      return initialState;
    default:
      return state;
  }
};
const ActionBar = ({ dispatch }) => (
  <button onClick={() => dispatch({ type: 'RESTART_GAME' })}>Restart</button>
);
"""

_TACTICS_ENEMY_TURN_WIRED = """
const reducer = (state, action) => {
  switch (action.type) {
    case 'END_TURN': {
      const enemy = state.units.find(u => !u.isPlayer);
      const units = state.units.map(u =>
        u.id === enemy.id ? { ...u, hp: u.hp - 1, position: { x: u.position.x - 1, y: u.position.y } } : u
      );
      return { ...state, units, phase: 'player' };
    }
    default:
      return state;
  }
};
"""

_TACTICS_SELECT_NO_DISPATCH = """
const reducer = (state, action) => {
  switch (action.type) {
    case 'SELECT_UNIT':
      return { ...state, selectedUnitId: action.payload };
    default:
      return state;
  }
};
const Grid = () => <button>End Turn</button>;
"""

_TACTICS_SELECT_DISPATCH = """
const reducer = (state, action) => {
  switch (action.type) {
    case 'SELECT_UNIT':
      return { ...state, selectedUnitId: action.payload };
    default:
      return state;
  }
};
const Grid = ({ dispatch }) => (
  <div onClick={() => dispatch({ type: 'SELECT_UNIT', payload: 1 })}>Pick</div>
);
"""

_TACTICS_MOVE_NO_RANGE = """
const moveRange = 2;
const reducer = (state, action) => {
  switch (action.type) {
    case 'MOVE_UNIT': {
      const newUnits = state.units.map(u =>
        u.id === action.payload.unitId ? { ...u, position: action.payload.to } : u
      );
      return { ...state, units: newUnits };
    }
    case 'END_TURN': {
      const dx = 1;
      if (Math.abs(dx) <= 1) return state;
      return state;
    }
    default:
      return state;
  }
};
"""

_TACTICS_ATTACK_INPLACE = """
const reducer = (state, action) => {
  switch (action.type) {
    case 'ATTACK_UNIT': {
      const target = state.units.find(u => u.id === action.payload.targetId);
      if (target) {
        target.hp -= 10;
      }
      return state;
    }
    default:
      return state;
  }
};
"""

_TACTICS_ATTACK_NO_DISPATCH = """
const reducer = (state, action) => {
  switch (action.type) {
    case 'SELECT_UNIT':
      return { ...state, selectedUnitId: action.payload };
    case 'ATTACK_UNIT': {
      const units = state.units.map(u =>
        u.id === action.payload.targetId ? { ...u, hp: u.hp - 10 } : u);
      return { ...state, units };
    }
    default:
      return state;
  }
};
const Grid = ({ dispatch }) => (
  <div onClick={() => dispatch({ type: 'SELECT_UNIT', payload: 1 })}>Pick</div>
);
"""

_TACTICS_ATTACK_ENEMY_CLICK = """
const attackRange = 1;
const reducer = (state, action) => {
  switch (action.type) {
    case 'SELECT_UNIT':
      return { ...state, selectedUnitId: action.payload };
    case 'ATTACK_UNIT': {
      const attacker = state.units.find(u => u.id === action.payload.attackerId);
      const target = state.units.find(u => u.id === action.payload.targetId);
      const dist = Math.abs(attacker.position.x - target.position.x)
        + Math.abs(attacker.position.y - target.position.y);
      if (dist > attackRange) return state;
      const units = state.units.map(u =>
        u.id === action.payload.targetId ? { ...u, hp: u.hp - 10 } : u);
      return { ...state, units };
    }
    default:
      return state;
  }
};
const Grid = ({ dispatch, state }) => (
  <div onClick={() => {
    const enemy = state.units.find(u => !u.isPlayer);
    dispatch({ type: 'ATTACK_UNIT', payload: { attackerId: state.selectedUnitId, targetId: enemy.id } });
  }}>Attack enemy</div>
);
"""

_TACTICS_ATTACK_NO_PLAYER_RANGE = """
const reducer = (state, action) => {
  switch (action.type) {
    case 'ATTACK_UNIT': {
      const units = state.units.map(u =>
        u.id === action.payload.targetId ? { ...u, hp: u.hp - 10 } : u);
      return { ...state, units };
    }
    case 'END_TURN': {
      const dx = 1;
      const dy = 0;
      if (Math.abs(dx) <= 1 && Math.abs(dy) <= 1) {
        const units = state.units.map(u =>
          !u.isPlayer ? { ...u, hp: u.hp - 1 } : u);
        return { ...state, units };
      }
      return state;
    }
    default:
      return state;
  }
};
const Grid = ({ dispatch }) => (
  <button onClick={() => dispatch({ type: 'ATTACK_UNIT', payload: { attackerId: 1, targetId: 2 } })}>Attack</button>
);
"""

_TACTICS_CELL_CLICK_ATTACK_WITH_RANGE = """
const manhattanDistance = (a, b) => Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
const reducer = (state, action) => {
  switch (action.type) {
    case 'CELL_CLICK': {
      const selectedUnit = state.selectedUnit;
      const targetCell = state.grid[action.rowIndex][action.colIndex];
      if (selectedUnit && targetCell?.type === 'enemy') {
        const enemyUnit = state.enemyUnits.find(u => u.id === targetCell.unitId);
        if (enemyUnit && manhattanDistance(selectedUnit, enemyUnit) <= 1) {
          const enemyUnits = state.enemyUnits.map(u =>
            u.id === enemyUnit.id ? { ...u, hp: u.hp - 1 } : u);
          return { ...state, enemyUnits };
        }
      }
      return state;
    }
    default:
      return state;
  }
};
const Grid = ({ dispatch }) => (
  <div onClick={() => dispatch({ type: 'CELL_CLICK', rowIndex: 1, colIndex: 1 })} />
);
"""

_TACTICS_RESTART_NOOP_INIT = """
export const initialState = {
  units: [{ id: 'p1', hp: 3, position: [0, 0] }, { id: 'e1', hp: 2, position: [4, 4] }],
  selectedUnit: null,
  gameState: 'playing',
};
export const gameReducer = (state, action) => {
  switch (action.type) {
    case 'INIT':
      return { ...state };
    default:
      return state;
  }
};
const ResultsPanel = ({ dispatch }) => (
  <button onClick={() => dispatch({ type: 'INIT' })}>Restart</button>
);
"""


class TestTacticsScaffoldQuality:
    def _files(self, *pairs):
        return list(pairs)

    def _plan(self):
        plan = _plan()
        plan.user_message = _TACTICS_GATE_PROMPT
        return plan

    def test_empty_player_enemy_units_flagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/gameReducer.ts", _TACTICS_SHELL_REDUCER)),
            plan=self._plan(),
        )
        assert any(i.code == "tactics_empty_unit_seed" for i in issues)

    def test_seeded_player_enemy_units_not_overflagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/gameReducer.ts", _TACTICS_SEEDED_INITIAL_STATE)),
            plan=self._plan(),
        )
        assert not any(i.code == "tactics_empty_unit_seed" for i in issues)

    def test_init_defined_but_not_dispatched_flagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(
                ("src/gameReducer.ts", _TACTICS_SHELL_REDUCER),
                ("src/Game.tsx", _TACTICS_SHELL_GAME),
            ),
            plan=self._plan(),
        )
        assert any(i.code == "tactics_seed_not_applied" for i in issues)

    def test_mounted_init_accepted(self):
        issues = inspect_generated_scaffold_quality(
            self._files(
                ("src/gameReducer.ts", _TACTICS_MOUNTED_INIT_REDUCER),
                ("src/App.tsx", _TACTICS_MOUNTED_INIT_GAME),
            ),
            plan=self._plan(),
        )
        assert not any(i.code == "tactics_seed_not_applied" for i in issues)

    def test_reducer_actions_without_ui_dispatch_flagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/Game.tsx", _TACTICS_UNWIRED_ACTIONS)),
            plan=self._plan(),
        )
        assert any(i.code == "tactics_action_not_wired" for i in issues)
        assert any("SELECT_UNIT" in i.message for i in issues if i.code == "tactics_action_not_wired")

    def test_select_unit_without_ui_dispatch_flagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _TACTICS_SELECT_NO_DISPATCH)),
            plan=self._plan(),
        )
        assert any(
            i.code == "tactics_action_not_wired" and "SELECT_UNIT" in i.message for i in issues
        )

    def test_player_unit_select_dispatch_accepted(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _TACTICS_SELECT_DISPATCH)),
            plan=self._plan(),
        )
        assert not any(i.code == "tactics_action_not_wired" for i in issues)

    def test_move_unit_without_range_check_flagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/gameReducer.ts", _TACTICS_MOVE_NO_RANGE)),
            plan=self._plan(),
        )
        assert any(i.code == "tactics_missing_movement_range" for i in issues)

    def test_move_unit_with_manhattan_range_accepted(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _TACTICS_WIRED_APP)),
            plan=self._plan(),
        )
        assert not any(i.code == "tactics_missing_movement_range" for i in issues)

    def test_attack_unit_inplace_mutation_flagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/gameReducer.ts", _TACTICS_ATTACK_INPLACE)),
            plan=self._plan(),
        )
        assert any(i.code == "tactics_inplace_attack_mutation" for i in issues)

    def test_attack_unit_without_ui_dispatch_flagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _TACTICS_ATTACK_NO_DISPATCH)),
            plan=self._plan(),
        )
        assert any(
            i.code == "tactics_action_not_wired"
            and "ATTACK_UNIT" in i.message
            for i in issues
        )

    def test_enemy_click_dispatching_attack_unit_accepted(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _TACTICS_ATTACK_ENEMY_CLICK)),
            plan=self._plan(),
        )
        assert not any(
            i.code == "tactics_action_not_wired"
            and (
                "ATTACK_UNIT" in i.message
                or "ATTACK/ATTACK_UNIT" in i.message
            )
            for i in issues
        )

    def test_attack_without_player_range_check_flagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _TACTICS_ATTACK_NO_PLAYER_RANGE)),
            plan=self._plan(),
        )
        assert any(i.code == "tactics_missing_attack_range" for i in issues)

    def test_enemy_only_attack_range_does_not_satisfy_player_attack(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/gameReducer.ts", _TACTICS_ATTACK_NO_PLAYER_RANGE)),
            plan=self._plan(),
        )
        assert any(
            i.code == "tactics_missing_attack_range"
            and "enemy-turn" in i.message.lower()
            for i in issues
        )

    def test_player_attack_with_range_check_accepted(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _TACTICS_WIRED_APP)),
            plan=self._plan(),
        )
        assert not any(i.code == "tactics_missing_attack_range" for i in issues)

    def test_cell_click_attack_with_manhattan_range_accepted(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _TACTICS_CELL_CLICK_ATTACK_WITH_RANGE)),
            plan=self._plan(),
        )
        assert not any(i.code == "tactics_missing_attack_range" for i in issues)

    def test_attack_unit_immutable_update_accepted(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _TACTICS_WIRED_APP)),
            plan=self._plan(),
        )
        assert not any(i.code == "tactics_inplace_attack_mutation" for i in issues)

    def test_restart_init_empty_reseed_flagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(
                ("src/gameReducer.ts", _TACTICS_RESTART_NOOP_INIT),
                ("src/components/TacticsResultsPanel.tsx", _TACTICS_RESTART_NOOP_INIT),
            ),
            plan=self._plan(),
        )
        assert any(i.code == "tactics_restart_not_seeded" for i in issues)

    def test_grid_without_click_handlers_flagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(
                ("src/gameReducer.ts", _TACTICS_SHELL_REDUCER),
                ("src/components/TacticsGridBoard.tsx", _TACTICS_SHELL_GRID),
            ),
            plan=self._plan(),
        )
        assert any(i.code == "tactics_grid_not_wired" for i in issues)

    def test_wired_select_move_attack_not_overflagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _TACTICS_WIRED_APP)),
            plan=self._plan(),
        )
        assert not any(i.code == "tactics_action_not_wired" for i in issues)
        assert not any(i.code == "tactics_grid_not_wired" for i in issues)

    def test_missing_enemy_turn_flagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/gameReducer.ts", _TACTICS_SHELL_REDUCER)),
            plan=self._plan(),
        )
        assert any(i.code == "tactics_enemy_turn_not_wired" for i in issues)

    def test_enemy_turn_mutation_accepted(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/gameReducer.ts", _TACTICS_ENEMY_TURN_WIRED)),
            plan=self._plan(),
        )
        assert not any(i.code == "tactics_enemy_turn_not_wired" for i in issues)

    def test_missing_battle_result_flagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/gameReducer.ts", _TACTICS_SHELL_REDUCER)),
            plan=self._plan(),
        )
        assert any(i.code == "tactics_missing_battle_result" for i in issues)

    def test_restart_empty_state_flagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(
                ("src/gameReducer.ts", _TACTICS_RESTART_EMPTY),
                ("src/components/TacticsActionBar.tsx", _TACTICS_RESTART_EMPTY),
            ),
            plan=self._plan(),
        )
        assert any(i.code == "tactics_restart_not_seeded" for i in issues)

    def test_restart_reseeds_units_accepted(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _TACTICS_WIRED_APP)),
            plan=self._plan(),
        )
        assert not any(i.code == "tactics_restart_not_seeded" for i in issues)

    def test_tactics_restart_not_mislabeled_as_deck_builder_missing_restart(self):
        issues = inspect_generated_scaffold_quality(
            self._files(
                ("src/gameReducer.ts", _TACTICS_SHELL_REDUCER),
                ("src/components/TacticsActionBar.tsx", "const ActionBar = () => <button>Restart</button>;"),
            ),
            plan=self._plan(),
        )
        assert not any(i.code == "missing_restart_action" for i in issues)

    def test_initial_shell_flags_multiple_tactics_issues(self):
        issues = inspect_generated_scaffold_quality(
            self._files(
                ("src/gameReducer.ts", _TACTICS_SHELL_REDUCER),
                ("src/Game.tsx", _TACTICS_SHELL_GAME),
                ("src/components/TacticsGridBoard.tsx", _TACTICS_SHELL_GRID),
            ),
            plan=self._plan(),
        )
        codes = {i.code for i in issues}
        assert "tactics_empty_unit_seed" in codes
        assert "tactics_seed_not_applied" in codes
        assert "tactics_action_not_wired" in codes or "tactics_grid_not_wired" in codes


_CITY_BUILDER_GATE_PROMPT = (
    "Build a browser city-building game on a small 5x5 grid where the player "
    "places houses, farms, wells, and power buildings, advances days to produce "
    "food and coins, grows population and happiness, wins by reaching a population "
    "goal by day 10, loses if food runs out, and can restart the city."
)

_CITY_SHELL_APP = """
const initialState = {
  grid: Array(5).fill(null).map(() => Array(5).fill(null)),
  food: 10, coins: 10, day: 1, population: 0, happiness: 100,
};
const reducer = (state, action) => {
  switch (action.type) {
    case 'PLACE_BUILDING': {
      const newGrid = [...state.grid];
      newGrid[action.payload.row][action.payload.col] = action.payload.building;
      return { ...state, grid: newGrid };
    }
    case 'END_DAY': {
      const newFood = state.food - state.grid.flat().filter(b => b === 'farm').length;
      const newCoins = state.coins + state.grid.flat().filter(b => b !== null).length;
      return { ...state, food: newFood, coins: newCoins, day: state.day + 1 };
    }
    case 'RESTART':
      return initialState;
    default:
      return state;
  }
};
"""

_CITY_SHELL_GRID = """
const CityGridBoard = ({ dispatch }) => {
  const handlePlaceBuilding = (row, col) => {
    dispatch({ type: 'PLACE_BUILDING', payload: { row, col, building: 'house' } });
  };
  return <div onClick={() => handlePlaceBuilding(0, 0)} />;
};
"""

_CITY_PALETTE_GOOD = """
const BUILDING_TYPES = ['house', 'farm', 'well', 'power'];
const [selectedBuilding, setSelectedBuilding] = useState('house');
const BuildingPalette = () => (
  <>
    <button onClick={() => setSelectedBuilding('house')}>House</button>
    <button onClick={() => setSelectedBuilding('farm')}>Farm</button>
    <button onClick={() => setSelectedBuilding('well')}>Well</button>
    <button onClick={() => setSelectedBuilding('power')}>Power</button>
  </>
);
dispatch({ type: 'PLACE_BUILDING', payload: { row, col, building: selectedBuilding } });
"""

_CITY_PLACEMENT_NO_GUARD = _CITY_SHELL_APP

_CITY_PLACEMENT_GUARD_GOOD = """
const reducer = (state, action) => {
  switch (action.type) {
    case 'PLACE_BUILDING': {
      if (state.grid[action.payload.row][action.payload.col] !== null) {
        return state;
      }
      const newGrid = [...state.grid];
      newGrid[action.payload.row][action.payload.col] = action.payload.building;
      return { ...state, grid: newGrid };
    }
    default:
      return state;
  }
};
"""

_CITY_PLACEMENT_UI_GUARD_GOOD = """
const CityGridBoard = () => {
  return row.map((cell, colIndex) => (
    <div onClick={() => {
      if (!cell) {
        dispatch({ type: 'PLACE_BUILDING', payload: { rowIndex, colIndex } });
      } else {
        alert('Invalid placement! Cell is already occupied.');
      }
    }}></div>
  ));
};
const reducer = (state, action) => {
  switch (action.type) {
    case 'PLACE_BUILDING':
      const newGrid = [...state.grid];
      newGrid[action.payload.rowIndex][action.payload.colIndex] = state.selectedBuilding;
      return { ...state, grid: newGrid };
    default:
      return state;
  }
};
"""

_CITY_PRODUCTION_HELPER_GOOD = """
const cityReducer = (state, action) => {
  switch (action.type) {
    case 'END_DAY':
      return produceDayResults(state);
    default:
      return state;
  }
};
const produceDayResults = (state) => {
  const farms = state.grid.flat().filter(b => b === 'farm').length;
  const wells = state.grid.flat().filter(b => b === 'well').length;
  return {
    ...state,
    food: state.food + farms * 2,
    coins: state.coins + state.grid.flat().filter(b => b !== null).length,
    population: state.population + state.grid.flat().filter(b => b === 'house').length,
    happiness: state.happiness + wells * 2,
    day: state.day + 1,
  };
};
"""

_CITY_PRODUCTION_DISPLAY_ONLY = """
const reducer = (state, action) => {
  switch (action.type) {
    case 'END_DAY':
      return { ...state, day: state.day + 1 };
    default:
      return state;
  }
};
const ResourceStatus = () => <div>Food: {state.food} Coins: {state.coins}</div>;
"""

_CITY_PRODUCTION_GOOD = """
const reducer = (state, action) => {
  switch (action.type) {
    case 'END_DAY': {
      const farms = state.grid.flat().filter(b => b === 'farm').length;
      const buildings = state.grid.flat().filter(b => b !== null).length;
      return {
        ...state,
        food: state.food + farms * 2 - state.population,
        coins: state.coins + buildings,
        day: state.day + 1,
      };
    }
    default:
      return state;
  }
};
"""

_CITY_PRODUCTION_HARDCODED = """
const endDay = () => {
  let newFood = resources.food - Math.floor(population / 5);
  setResources({ ...resources, food: newFood });
  setDay(day + 1);
};
"""

_CITY_PRODUCTION_CATALOG_UNUSED = """
const BUILDING_PRODUCTION = {
  farm: { food: 2, coins: 0 },
  house: { food: 0, coins: 1 },
  well: { food: 1, coins: 0 },
  power: { food: 0, coins: 2 },
};
const endDay = () => {
  setResources({ ...resources, food: resources.food + 1, coins: resources.coins + 1 });
  setDay(day + 1);
};
"""

_CITY_POPULATION_STATIC = _CITY_SHELL_APP + """
const ResourceStatus = ({ population, happiness }) => (
  <div>Population: {population} Happiness: {happiness}</div>
);
"""

_CITY_POPULATION_WIRED = """
const reducer = (state, action) => {
  switch (action.type) {
    case 'END_DAY': {
      const houses = state.grid.flat().filter(b => b === 'house').length;
      const wells = state.grid.flat().filter(b => b === 'well').length;
      return {
        ...state,
        population: state.population + houses,
        happiness: Math.min(100, state.happiness + wells * 2),
        day: state.day + 1,
      };
    }
    default:
      return state;
  }
};
"""

_CITY_HAPPINESS_ABSENT = """
const [population, setPopulation] = useState(0);
const ResourceStatus = () => <div>Population: {population}</div>;
const endDay = () => setPopulation(population + 1);
"""

_CITY_HAPPINESS_WIRED = """
const [happiness, setHappiness] = useState(50);
const endDay = () => {
  const wells = grid.flat().filter((cell) => cell === 'well').length;
  const farms = grid.flat().filter((cell) => cell === 'farm').length;
  setHappiness(Math.min(100, happiness + wells * 2 + farms));
  setResources({ ...resources, food: resources.food + farms * 2, coins: resources.coins + 1 });
};
const ResourceStatus = () => <div>Happiness: {happiness}</div>;
"""

_CITY_HAPPINESS_HARDCODED_ONE = """
const produceDayResults = (state) => {
  const farms = state.grid.flat().filter(b => b === 'farm').length;
  const happinessChange = 1;
  const newHappiness = state.happiness + happinessChange;
  return { ...state, food: state.food + farms, happiness: newHappiness, day: state.day + 1 };
};
const cityReducer = (state, action) => {
  switch (action.type) {
    case 'END_DAY':
      return produceDayResults(state);
    default:
      return state;
  }
};
"""

_CITY_HAPPINESS_SET_PLUS_ONE = """
const [happiness, setHappiness] = useState(50);
const endDay = () => {
  setHappiness(happiness + 1);
};
"""

_CITY_HAPPINESS_WELLS_DERIVED = """
const produceDayResults = (state) => {
  const wells = state.grid.flat().filter(b => b === 'well').length;
  const power = state.grid.flat().filter(b => b === 'power').length;
  return {
    ...state,
    happiness: state.happiness + wells * 3 + power * 2,
    day: state.day + 1,
  };
};
"""

_CITY_HAPPINESS_FOOD_PRESSURE = """
const endDay = () => {
  const farms = grid.flat().filter((cell) => cell === 'farm').length;
  const newFood = resources.food + farms - population;
  const happinessDelta = newFood <= 0 ? -10 : wells * 2;
  setHappiness(Math.max(0, happiness + happinessDelta));
};
const wells = grid.flat().filter((cell) => cell === 'well').length;
"""

_CITY_GOAL_MISSING = _CITY_SHELL_APP + """
useEffect(() => {
  if (state.day > 10 || state.food <= 0) setGameOver(true);
}, [state.day, state.food]);
"""

_CITY_GOAL_WIRED = """
const POPULATION_GOAL = 20;
if (state.population >= POPULATION_GOAL && state.day <= 10) {
  setGameState('win');
}
if (state.food <= 0) {
  setGameState('lose');
}
"""

_CITY_FOOD_FAIL_MISSING = """
const reducer = (state, action) => {
  switch (action.type) {
    case 'END_DAY':
      return { ...state, day: state.day + 1, food: state.food - 1 };
    default:
      return state;
  }
};
useEffect(() => {
  if (state.day > 10) setGameOver(true);
}, [state.day]);
"""

_CITY_FOOD_FAIL_WIRED = """
useEffect(() => {
  if (state.food <= 0) setGameOver(true);
}, [state.food]);
"""

_CITY_RESTART_NOOP = """
const reducer = (state, action) => {
  switch (action.type) {
    case 'INIT':
      return { ...state };
    case 'RESTART':
      return reducer(state, { type: 'INIT' });
    default:
      return state;
  }
};
const ResultsPanel = ({ dispatch }) => (
  <button onClick={() => dispatch({ type: 'RESTART' })}>New City</button>
);
"""

_CITY_POPULATION_USESTATE_GOOD = """
const [population, setPopulation] = useState(0);
const endDay = () => {
  let newPopulation = population + 2;
  setPopulation(newPopulation);
};
"""

_CITY_RESTART_GOOD = """
const initialState = {
  grid: Array(5).fill(null).map(() => Array(5).fill(null)),
  food: 10, coins: 10, day: 1, population: 0, happiness: 100,
};
const reducer = (state, action) => {
  switch (action.type) {
    case 'RESTART':
      return initialState;
    default:
      return state;
  }
};
"""


_CITY_RESTART_USESTATE_GOOD = """
const restartGame = () => {
  setGrid(Array(5).fill(null).map(() => Array(5).fill(null)));
  setResources(INITIAL_RESOURCES);
  setDay(1);
  setPopulation(0);
  setGameResult(null);
};
<button onClick={restartGame}>New City</button>
"""


class TestCityBuilderScaffoldQuality:
    def _files(self, *pairs):
        return list(pairs)

    def _plan(self):
        plan = _plan()
        plan.user_message = _CITY_BUILDER_GATE_PROMPT
        return plan

    def test_missing_palette_and_single_house_flagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(
                ("src/App.tsx", _CITY_SHELL_APP),
                ("src/components/CityGridBoard.tsx", _CITY_SHELL_GRID),
            ),
            plan=self._plan(),
        )
        codes = {i.code for i in issues}
        assert "city_missing_building_palette" in codes
        assert "city_single_building_only" in codes

    def test_selectable_building_palette_accepted(self):
        issues = inspect_generated_scaffold_quality(
            self._files(
                ("src/App.tsx", _CITY_PALETTE_GOOD),
                ("src/components/BuildingPalette.tsx", _CITY_PALETTE_GOOD),
            ),
            plan=self._plan(),
        )
        assert not any(i.code == "city_missing_building_palette" for i in issues)
        assert not any(i.code == "city_single_building_only" for i in issues)

    def test_placement_overwrite_flagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _CITY_PLACEMENT_NO_GUARD)),
            plan=self._plan(),
        )
        assert any(i.code == "city_invalid_placement_not_blocked" for i in issues)

    def test_occupied_cell_guard_accepted(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _CITY_PLACEMENT_GUARD_GOOD)),
            plan=self._plan(),
        )
        assert not any(i.code == "city_invalid_placement_not_blocked" for i in issues)

    def test_ui_placement_guard_accepted(self):
        issues = inspect_generated_scaffold_quality(
            self._files(
                ("src/App.tsx", _CITY_PLACEMENT_UI_GUARD_GOOD),
                ("src/components/CityGridBoard.tsx", _CITY_PLACEMENT_UI_GUARD_GOOD),
            ),
            plan=self._plan(),
        )
        assert not any(i.code == "city_invalid_placement_not_blocked" for i in issues)

    def test_end_day_helper_production_accepted(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/state/cityState.tsx", _CITY_PRODUCTION_HELPER_GOOD)),
            plan=self._plan(),
        )
        assert not any(i.code == "city_production_not_wired" for i in issues)
        assert not any(i.code == "city_population_not_wired" for i in issues)
        assert not any(i.code == "city_happiness_not_wired" for i in issues)

    def test_end_day_display_only_resources_flagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _CITY_PRODUCTION_DISPLAY_ONLY)),
            plan=self._plan(),
        )
        assert any(
            i.code in {"city_production_not_wired", "city_resources_display_only"} for i in issues
        )

    def test_end_day_grid_production_accepted(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _CITY_PRODUCTION_GOOD)),
            plan=self._plan(),
        )
        assert not any(i.code == "city_production_not_wired" for i in issues)
        assert not any(i.code == "city_resources_display_only" for i in issues)

    def test_end_day_hardcoded_production_flagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _CITY_PRODUCTION_HARDCODED)),
            plan=self._plan(),
        )
        assert any(i.code == "city_production_not_wired" for i in issues)

    def test_unused_building_production_catalog_flagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _CITY_PRODUCTION_CATALOG_UNUSED)),
            plan=self._plan(),
        )
        assert any(i.code == "city_production_not_wired" for i in issues)

    def test_population_happiness_display_only_flagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _CITY_POPULATION_STATIC)),
            plan=self._plan(),
        )
        assert any(i.code == "city_population_not_wired" for i in issues)
        assert any(i.code == "city_happiness_not_wired" for i in issues)

    def test_happiness_absent_flagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _CITY_HAPPINESS_ABSENT)),
            plan=self._plan(),
        )
        assert any(i.code == "city_happiness_not_wired" for i in issues)

    def test_happiness_and_grid_production_accepted(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _CITY_HAPPINESS_WIRED)),
            plan=self._plan(),
        )
        assert not any(i.code == "city_happiness_not_wired" for i in issues)
        assert not any(i.code == "city_production_not_wired" for i in issues)

    def test_hardcoded_happiness_change_flagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/state/cityState.tsx", _CITY_HAPPINESS_HARDCODED_ONE)),
            plan=self._plan(),
        )
        assert any(i.code == "city_happiness_not_wired" for i in issues)

    def test_set_happiness_plus_one_without_grid_flagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _CITY_HAPPINESS_SET_PLUS_ONE)),
            plan=self._plan(),
        )
        assert any(i.code == "city_happiness_not_wired" for i in issues)

    def test_happiness_from_wells_power_grid_accepted(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/state/cityState.tsx", _CITY_HAPPINESS_WELLS_DERIVED)),
            plan=self._plan(),
        )
        assert not any(i.code == "city_happiness_not_wired" for i in issues)

    def test_happiness_from_food_pressure_accepted(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _CITY_HAPPINESS_FOOD_PRESSURE)),
            plan=self._plan(),
        )
        assert not any(i.code == "city_happiness_not_wired" for i in issues)

    def test_population_happiness_mutation_accepted(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _CITY_POPULATION_WIRED)),
            plan=self._plan(),
        )
        assert not any(i.code == "city_population_not_wired" for i in issues)
        assert not any(i.code == "city_happiness_not_wired" for i in issues)

    def test_missing_population_goal_win_flagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _CITY_GOAL_MISSING)),
            plan=self._plan(),
        )
        assert any(i.code == "city_goal_not_wired" for i in issues)

    def test_missing_food_loss_fail_flagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _CITY_FOOD_FAIL_MISSING)),
            plan=self._plan(),
        )
        assert any(i.code == "city_fail_condition_not_wired" for i in issues)

    def test_population_goal_and_food_fail_accepted(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _CITY_GOAL_WIRED + _CITY_FOOD_FAIL_WIRED)),
            plan=self._plan(),
        )
        assert not any(i.code == "city_goal_not_wired" for i in issues)
        assert not any(i.code == "city_fail_condition_not_wired" for i in issues)

    def test_population_usestate_mutation_accepted(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _CITY_POPULATION_USESTATE_GOOD)),
            plan=self._plan(),
        )
        assert not any(i.code == "city_population_not_wired" for i in issues)

    def test_restart_usestate_reseed_accepted(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _CITY_RESTART_USESTATE_GOOD)),
            plan=self._plan(),
        )
        assert not any(i.code == "city_restart_not_seeded" for i in issues)

    def test_restart_noop_flagged(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _CITY_RESTART_NOOP)),
            plan=self._plan(),
        )
        assert any(i.code == "city_restart_not_seeded" for i in issues)

    def test_restart_reseeds_city_accepted(self):
        issues = inspect_generated_scaffold_quality(
            self._files(("src/App.tsx", _CITY_RESTART_GOOD)),
            plan=self._plan(),
        )
        assert not any(i.code == "city_restart_not_seeded" for i in issues)

    def test_initial_shell_flags_multiple_city_issues(self):
        issues = inspect_generated_scaffold_quality(
            self._files(
                ("src/App.tsx", _CITY_SHELL_APP),
                ("src/components/CityGridBoard.tsx", _CITY_SHELL_GRID),
            ),
            plan=self._plan(),
        )
        codes = {i.code for i in issues}
        assert "city_missing_building_palette" in codes
        assert "city_single_building_only" in codes
        assert "city_invalid_placement_not_blocked" in codes
        assert "city_population_not_wired" in codes
        assert "city_happiness_not_wired" in codes
        assert "city_goal_not_wired" in codes


_DASHBOARD_GATE_PROMPT = (
    "Build a read-only dashboard overview for a developer tool team. Include 4 KPI cards, "
    "a line chart for build quality over time, a bar chart for issue categories, a simple "
    "recent builds table, a local filter bar, empty/loading/error state examples, meaningful "
    "sample data, responsive layout, and accessible headings/table structure. No backend, "
    "no auth, no CRUD, no live data."
)

_DASHBOARD_CHART_PAIR_PROMPT = (
    "Build a read-only dashboard overview with KPI cards, a line chart for build quality over "
    "time, a bar chart for issue categories, and a simple recent builds table."
)

_DASHBOARD_NO_FILTER_APP = """
const Dashboard = () => (
  <>
    <header><h1>Developer Tool Dashboard</h1></header>
    <nav aria-label="Primary dashboard nav"><a href="/overview">Overview</a></nav>
    <main>
      <section>
        <h2>Build quality over time (line chart)</h2>
        <p>Line chart with build quality by week.</p>
      </section>
      <section>
        <h2>Issues by category (bar chart)</h2>
        <p>Bar chart grouped by issue category.</p>
      </section>
      <section role="status">Empty: no builds yet</section>
      <section role="status">Loading: sample dashboard state</section>
      <section role="alert">Error: unable to load sample dashboard state</section>
      <table>
        <thead><tr><th>Build</th></tr></thead>
        <tbody><tr><td>123</td></tr></tbody>
      </table>
    </main>
  </>
);
"""

_DASHBOARD_FILTER_WIRED_APP = """
const Dashboard = () => {
  const [selectedStatus, setSelectedStatus] = useState('all');
  const rows = [{ id: 1, status: 'success' }, { id: 2, status: 'failed' }];
  const filteredRows = rows.filter((row) => selectedStatus === 'all' || row.status === selectedStatus);
  return (
    <>
      <header><h1>Developer Tool Dashboard</h1></header>
      <nav aria-label="Primary dashboard nav"><a href="/overview">Overview</a></nav>
      <main>
        <label htmlFor="status-filter">Filter builds</label>
        <select
          id="status-filter"
          value={selectedStatus}
          onChange={(event) => setSelectedStatus(event.target.value)}
        >
          <option value="all">All</option>
          <option value="success">Success</option>
          <option value="failed">Failed</option>
        </select>
        <section>
          <h2>Build quality over time (line chart)</h2>
          <p>Line chart with build quality by week.</p>
        </section>
        <section>
          <h2>Issues by category (bar chart)</h2>
          <p>Bar chart grouped by issue category.</p>
        </section>
        <section role="status">Empty: no builds match filters</section>
        <section role="status">Loading: sample dashboard state</section>
        <section role="alert">Error: unable to load sample dashboard state</section>
        <table>
          <thead><tr><th>Build</th><th>Status</th></tr></thead>
          <tbody>
            {filteredRows.map((row) => (
              <tr key={row.id}><td>{row.id}</td><td>{row.status}</td></tr>
            ))}
          </tbody>
        </table>
      </main>
    </>
  );
};
"""

_DASHBOARD_FILTER_DEAD_APP = """
const Dashboard = () => (
  <>
    <header><h1>Developer Tool Dashboard</h1></header>
    <nav aria-label="Primary dashboard nav"><a href="/overview">Overview</a></nav>
    <main>
      <label htmlFor="status-filter">Filter builds</label>
      <select id="status-filter">
        <option>All</option>
        <option>Success</option>
      </select>
      <section>
        <h2>Build quality over time (line chart)</h2>
        <p>Line chart with build quality by week.</p>
      </section>
      <section>
        <h2>Issues by category (bar chart)</h2>
        <p>Bar chart grouped by issue category.</p>
      </section>
      <section role="status">Empty: no builds match filters</section>
      <section role="status">Loading: sample dashboard state</section>
      <section role="alert">Error: unable to load sample dashboard state</section>
      <table>
        <thead><tr><th>Build</th></tr></thead>
        <tbody><tr><td>123</td></tr></tbody>
      </table>
    </main>
  </>
);
"""

_DASHBOARD_EMPTY_ONLY_APP = """
const Dashboard = () => {
  const [selectedStatus, setSelectedStatus] = useState('all');
  const rows = [{ id: 1, status: 'success' }];
  const filteredRows = rows.filter((row) => selectedStatus === 'all' || row.status === selectedStatus);
  return (
    <>
      <header><h1>Developer Tool Dashboard</h1></header>
      <nav aria-label="Primary dashboard nav"><a href="/overview">Overview</a></nav>
      <main>
        <label htmlFor="status-filter">Filter builds</label>
        <input id="status-filter" value={selectedStatus} onChange={(event) => setSelectedStatus(event.target.value)} />
        <section><h2>Build quality over time (line chart)</h2></section>
        <section><h2>Issues by category (bar chart)</h2></section>
        <section role="status">Empty: no builds match filters</section>
        <table>
          <thead><tr><th>Build</th></tr></thead>
          <tbody>{filteredRows.map((row) => <tr key={row.id}><td>{row.id}</td></tr>)}</tbody>
        </table>
      </main>
    </>
  );
};
"""

_DASHBOARD_MISSING_LANDMARKS_APP = """
const Dashboard = () => {
  const [selectedStatus, setSelectedStatus] = useState('all');
  const rows = [{ id: 1, status: 'success' }];
  const filteredRows = rows.filter((row) => selectedStatus === 'all' || row.status === selectedStatus);
  return (
    <section>
      <h1>Developer Tool Dashboard</h1>
      <label htmlFor="status-filter">Filter builds</label>
      <input id="status-filter" value={selectedStatus} onChange={(event) => setSelectedStatus(event.target.value)} />
      <section><h2>Build quality over time (line chart)</h2></section>
      <section><h2>Issues by category (bar chart)</h2></section>
      <section role="status">Empty: no builds match filters</section>
      <section role="status">Loading: sample dashboard state</section>
      <section role="alert">Error: unable to load sample dashboard state</section>
      <table>
        <thead><tr><th>Build</th></tr></thead>
        <tbody>{filteredRows.map((row) => <tr key={row.id}><td>{row.id}</td></tr>)}</tbody>
      </table>
    </section>
  );
};
"""

_DASHBOARD_LINE_ONLY_APP = """
const Dashboard = () => (
  <>
    <header><h1>Developer Tool Dashboard</h1></header>
    <nav aria-label="Primary dashboard nav"><a href="/overview">Overview</a></nav>
    <main>
      <section><h2>Build quality over time (line chart)</h2></section>
      <table>
        <thead><tr><th>Build</th></tr></thead>
        <tbody><tr><td>123</td></tr></tbody>
      </table>
    </main>
  </>
);
"""


class TestDashboardScaffoldQuality:
    def _dashboard_plan(self, prompt: str = _DASHBOARD_GATE_PROMPT) -> Plan:
        plan = _plan()
        plan.user_message = prompt
        return plan

    def test_missing_requested_filter_is_flagged(self):
        issues = inspect_generated_scaffold_quality(
            [("src/Dashboard.tsx", _DASHBOARD_NO_FILTER_APP)],
            plan=self._dashboard_plan(),
        )
        assert any(i.code == "dashboard_missing_requested_filter" for i in issues)

    def test_filter_control_with_state_handler_and_mapping_is_accepted(self):
        issues = inspect_generated_scaffold_quality(
            [("src/Dashboard.tsx", _DASHBOARD_FILTER_WIRED_APP)],
            plan=self._dashboard_plan(),
        )
        assert not any(i.code == "dashboard_missing_requested_filter" for i in issues)
        assert not any(i.code == "dashboard_dead_filter_control" for i in issues)

    def test_dead_filter_control_is_flagged(self):
        issues = inspect_generated_scaffold_quality(
            [("src/Dashboard.tsx", _DASHBOARD_FILTER_DEAD_APP)],
            plan=self._dashboard_plan(),
        )
        assert any(i.code == "dashboard_dead_filter_control" for i in issues)

    def test_missing_loading_error_states_is_flagged(self):
        issues = inspect_generated_scaffold_quality(
            [("src/Dashboard.tsx", _DASHBOARD_EMPTY_ONLY_APP)],
            plan=self._dashboard_plan(),
        )
        assert any(i.code == "dashboard_missing_loading_error_states" for i in issues)

    def test_static_empty_loading_error_panels_are_accepted(self):
        issues = inspect_generated_scaffold_quality(
            [("src/Dashboard.tsx", _DASHBOARD_FILTER_WIRED_APP)],
            plan=self._dashboard_plan(),
        )
        assert not any(i.code == "dashboard_missing_loading_error_states" for i in issues)

    def test_missing_semantic_landmarks_is_flagged(self):
        issues = inspect_generated_scaffold_quality(
            [("src/Dashboard.tsx", _DASHBOARD_MISSING_LANDMARKS_APP)],
            plan=self._dashboard_plan(),
        )
        assert any(i.code == "dashboard_missing_semantic_landmarks" for i in issues)

    def test_semantic_landmarks_header_nav_main_h1_table_are_accepted(self):
        issues = inspect_generated_scaffold_quality(
            [("src/Dashboard.tsx", _DASHBOARD_FILTER_WIRED_APP)],
            plan=self._dashboard_plan(),
        )
        assert not any(i.code == "dashboard_missing_semantic_landmarks" for i in issues)

    def test_missing_requested_chart_type_is_flagged_when_prompt_requests_line_and_bar(self):
        issues = inspect_generated_scaffold_quality(
            [("src/Dashboard.tsx", _DASHBOARD_LINE_ONLY_APP)],
            plan=self._dashboard_plan(prompt=_DASHBOARD_CHART_PAIR_PROMPT),
        )
        assert any(i.code == "dashboard_missing_requested_chart_type" for i in issues)

    def test_dashboard_repair_prompt_includes_dashboard_focus_guidance(self):
        issues = [
            ScaffoldQualityIssue(
                code="dashboard_missing_requested_filter",
                message="Filter bar missing",
                path="src/Dashboard.tsx",
            ),
            ScaffoldQualityIssue(
                code="dashboard_missing_loading_error_states",
                message="Loading/error states missing",
                path="src/Dashboard.tsx",
            ),
            ScaffoldQualityIssue(
                code="dashboard_missing_semantic_landmarks",
                message="header/nav missing",
                path="src/Dashboard.tsx",
            ),
        ]
        messages = build_scaffold_repair_prompt(
            self._dashboard_plan(),
            [("src/Dashboard.tsx", _DASHBOARD_NO_FILTER_APP)],
            issues,
            base_system_prompt="BASE",
        )
        body = messages[0]["content"]
        assert "Dashboard repair focus" in body
        assert "local filter/search bar" in body
        assert "Empty / Loading / Error" in body
        assert "<header>" in body and "<nav>" in body and "<main>" in body
        assert "line and bar" in body.lower()
        assert "no backend/live data/auth/crud/payments" in body.lower()
        assert "valid JSON" in body


_SAAS_GATE_PROMPT = (
    "Build a static SaaS product dashboard for an AI developer platform. Include an app shell with "
    "sidebar and topbar, a workspace/project selector placeholder, usage cards, a plan/status card, "
    "recent activity, a simple project/resource list, one upgrade CTA, settings/help shortcuts, "
    "empty/loading/error state examples, responsive layout, and accessible header/nav/main/list/table "
    "structure. Use meaningful local sample data only. No backend, no auth, no billing or payments, "
    "no CRUD, no admin user management, no permissions, and no live data."
)

_SAAS_MISSING_STATES_AND_TABLE_APP = """
const App = () => (
  <div>
    <header><h1>Workspace dashboard</h1></header>
    <nav aria-label="Primary nav"><a href="#">Overview</a></nav>
    <main>
      <section><h2>Usage</h2><p>42% quota used</p></section>
      <section><h2>Plan status</h2><p>Starter</p></section>
      <section><h2>Recent activity</h2><ul><li>Project created</li></ul></section>
      <section><h2>Resources</h2><ul><li>Project Alpha</li></ul></section>
      <section role="status">Empty: no projects yet</section>
      <section><button>Upgrade</button><a href="#">Settings</a><a href="#">Help</a></section>
    </main>
  </div>
);
"""

_SAAS_GOOD_STATES_AND_TABLE_APP = """
const App = () => (
  <div>
    <header><h1>Workspace dashboard</h1></header>
    <nav aria-label="Primary nav"><a href="#">Overview</a></nav>
    <main>
      <section><h2>Usage</h2><p>42% quota used</p></section>
      <section><h2>Plan status</h2><p>Starter</p></section>
      <section><h2>Recent activity</h2><ul><li>Project created</li></ul></section>
      <section role="status">Empty: no resources in this workspace</section>
      <section role="status">Loading: sample static dashboard state</section>
      <section role="alert">Error: sample local error state only</section>
      <section>
        <h2>Project/resource table</h2>
        <table>
          <thead><tr><th>Project</th><th>Status</th></tr></thead>
          <tbody><tr><td>Alpha</td><td>Active</td></tr></tbody>
        </table>
      </section>
      <section><button>Upgrade</button><a href="#">Settings</a><a href="#">Help</a></section>
    </main>
  </div>
);
"""

_SAAS_ASYNC_FETCH_APP = """
const Dashboard = () => {
  const [loading, setLoading] = useState(true);
  const [rows, setRows] = useState([]);
  useEffect(() => {
    const fetchData = async () => {
      // Simulate API call
      setTimeout(() => {
        setRows([{ name: 'Alpha', status: 'Active' }]);
        setLoading(false);
      }, 800);
    };
    fetchData();
  }, []);
  if (loading) return <div>Loading...</div>;
  return (
    <div>
      <header><h1>Workspace dashboard</h1></header>
      <nav aria-label="Primary nav"><a href="#">Overview</a></nav>
      <main>
        <table><tbody>{rows.map((row) => <tr key={row.name}><td>{row.name}</td></tr>)}</tbody></table>
      </main>
    </div>
  );
};
"""


class TestSaaSDashboardScaffoldQuality:
    def _saas_plan(self, prompt: str = _SAAS_GATE_PROMPT) -> Plan:
        plan = _plan()
        plan.user_message = prompt
        return plan

    def test_missing_saas_loading_error_states_is_flagged(self):
        issues = inspect_generated_scaffold_quality(
            [("src/App.tsx", _SAAS_MISSING_STATES_AND_TABLE_APP)],
            plan=self._saas_plan(),
        )
        assert any(i.code == "saas_missing_loading_error_states" for i in issues)

    def test_missing_saas_semantic_resource_table_is_flagged(self):
        issues = inspect_generated_scaffold_quality(
            [("src/App.tsx", _SAAS_MISSING_STATES_AND_TABLE_APP)],
            plan=self._saas_plan(),
        )
        assert any(i.code == "saas_missing_semantic_resource_table" for i in issues)

    def test_saas_live_fetch_simulation_is_flagged(self):
        issues = inspect_generated_scaffold_quality(
            [("src/App.tsx", _SAAS_ASYNC_FETCH_APP)],
            plan=self._saas_plan(),
        )
        assert any(i.code == "saas_live_fetch_impl_detected" for i in issues)

    def test_saas_static_state_examples_and_semantic_table_are_accepted(self):
        issues = inspect_generated_scaffold_quality(
            [("src/App.tsx", _SAAS_GOOD_STATES_AND_TABLE_APP)],
            plan=self._saas_plan(),
        )
        assert not any(i.code == "saas_missing_loading_error_states" for i in issues)
        assert not any(i.code == "saas_missing_semantic_resource_table" for i in issues)

    def test_saas_repair_prompt_includes_saas_focus_guidance(self):
        issues = [
            ScaffoldQualityIssue(
                code="saas_missing_loading_error_states",
                message="Missing static empty/loading/error examples",
                path="src/App.tsx",
            ),
            ScaffoldQualityIssue(
                code="saas_missing_semantic_resource_table",
                message="Missing semantic table structure",
                path="src/App.tsx",
            ),
            ScaffoldQualityIssue(
                code="saas_live_fetch_impl_detected",
                message="Fetch simulation is present",
                path="src/App.tsx",
            ),
        ]
        messages = build_scaffold_repair_prompt(
            self._saas_plan(),
            [("src/App.tsx", _SAAS_MISSING_STATES_AND_TABLE_APP)],
            issues,
            base_system_prompt="BASE",
        )
        body = messages[0]["content"]
        assert "SaaS dashboard repair focus" in body
        assert "Empty / Loading / Error" in body
        assert "Do not use '/api', fetch(, axios, async backend simulation, or live polling" in body
        assert "<header>" in body and "<nav>" in body and "<main>" in body
        assert "<table>" in body
        assert "static SaaS lane" in body
        assert "valid JSON" in body

    def test_saas_repair_prompt_explicitly_bans_live_fetch_api_impl(self):
        issues = [
            ScaffoldQualityIssue(
                code="saas_live_fetch_impl_detected",
                message="Found fetch/useEffect/setTimeout API-style flow",
                path="src/App.tsx",
            )
        ]
        messages = build_scaffold_repair_prompt(
            self._saas_plan(),
            [("src/App.tsx", _SAAS_ASYNC_FETCH_APP)],
            issues,
            base_system_prompt="BASE",
        )
        body = messages[0]["content"]
        lowered = body.lower()
        assert "remove fetch/axios/api calls/useeffect live-loading simulations/timers/server endpoints" in lowered
        assert "do not use '/api', fetch(, axios, async backend simulation, or live polling" in lowered
        assert "never require fetch, async calls, api endpoints, backend, timers, polling, or live data" in lowered

    def test_saas_repair_prompt_requires_visible_static_state_examples(self):
        issues = [
            ScaffoldQualityIssue(
                code="saas_missing_loading_error_states",
                message="Missing empty/loading/error examples",
                path="src/App.tsx",
            )
        ]
        messages = build_scaffold_repair_prompt(
            self._saas_plan(),
            [("src/App.tsx", _SAAS_MISSING_STATES_AND_TABLE_APP)],
            issues,
            base_system_prompt="BASE",
        )
        body = messages[0]["content"]
        assert "rendered in UI (not comments/text-only)" in body
        assert "'No projects yet'" in body
        assert "'Loading preview example'" in body
        assert "'Unable to load local sample'" in body

    def test_saas_repair_prompt_requires_semantic_table_tags_for_rows(self):
        issues = [
            ScaffoldQualityIssue(
                code="saas_missing_semantic_resource_table",
                message="Missing semantic resource table",
                path="src/App.tsx",
            )
        ]
        messages = build_scaffold_repair_prompt(
            self._saas_plan(),
            [("src/App.tsx", _SAAS_MISSING_STATES_AND_TABLE_APP)],
            issues,
            base_system_prompt="BASE",
        )
        body = messages[0]["content"]
        assert "<thead>" in body
        assert "<tbody>" in body
        assert "<th>" in body
        assert "<td>" in body
        assert "Do not use div-soup cards pretending to be a table" in body


_ADMIN_GATE_PROMPT = (
    "Build a static admin dashboard for an AI developer platform. Include an admin shell with "
    "sidebar and topbar, overview/status cards, a user/team summary, a static role and permission "
    "summary, a review queue, a resource/user table, an audit/activity log, a system status panel, "
    "demo-mode action controls, visible empty/loading/error state examples, responsive layout, and "
    "accessible header/nav/main/table/list structure. Use meaningful local mock data only. No backend, "
    "no auth, no real RBAC, no permission mutation, no CRUD, no destructive actions, no live monitoring, "
    "no real audit logging, no billing or payments, and no production security claims."
)

_ADMIN_MISSING_STATES_APP = """
const App = () => (
  <div>
    <header><h1>Admin Dashboard</h1></header>
    <nav aria-label="Admin nav"><a href="#">Overview</a></nav>
    <main>
      <section><h2>Overview</h2><p>Status cards shown with local sample data.</p></section>
      <section><h2>User and team summary</h2><ul><li>Team Core</li></ul></section>
      <section><h2>Review queue</h2><ul><li>Pending moderation</li></ul></section>
      <section><h2>Resource/user table</h2>
        <table>
          <thead><tr><th>User</th><th>Status</th></tr></thead>
          <tbody><tr><td>Avery</td><td>Active</td></tr></tbody>
        </table>
      </section>
      <section><button disabled>Demo action</button><p>Read-only preview only.</p></section>
    </main>
  </div>
);
"""

_ADMIN_GOOD_STATES_TABLE_APP = """
const App = () => (
  <div>
    <header><h1>Admin Dashboard</h1></header>
    <nav aria-label="Admin nav"><a href="#">Overview</a></nav>
    <main>
      <section><h2>Overview and status cards</h2><p>Static local summary data.</p></section>
      <section><h2>User and team summary</h2><ul><li>Platform team</li></ul></section>
      <section><h2>Role and permission summary</h2><ul><li>Viewer: read-only</li></ul></section>
      <section><h2>Review queue</h2><ul><li>Pending review item</li></ul></section>
      <section>
        <h2>Resource/user table</h2>
        <table>
          <thead><tr><th>User</th><th>Status</th></tr></thead>
          <tbody><tr><td>Avery</td><td>Healthy</td></tr></tbody>
        </table>
      </section>
      <section><h2>Audit/activity log</h2><ul><li>Demo activity event</li></ul></section>
      <section><h2>System status panel</h2><p>Operational (static local sample)</p></section>
      <section><button disabled>Demo action</button><p>Read-only illustrative control.</p></section>
      <section aria-label="Static admin state examples">
        <div role="status">Empty: No users match this filter</div>
        <div role="status">Loading: Loading admin preview example</div>
        <div role="alert">Error: Unable to load local demo data</div>
      </section>
    </main>
  </div>
);
"""

_ADMIN_ASYNC_FETCH_APP = """
const Dashboard = () => {
  const [loading, setLoading] = useState(true);
  const [rows, setRows] = useState([]);
  useEffect(() => {
    const run = async () => {
      setTimeout(() => {
        setRows([{ name: 'Avery', status: 'Active' }]);
        setLoading(false);
      }, 500);
    };
    run();
  }, []);
  if (loading) return <div>Loading...</div>;
  return (
    <div>
      <header><h1>Admin Dashboard</h1></header>
      <nav aria-label="Admin nav"><a href="#">Overview</a></nav>
      <main>
        <table><tbody>{rows.map((row) => <tr key={row.name}><td>{row.name}</td></tr>)}</tbody></table>
      </main>
    </div>
  );
};
"""

_ADMIN_DESTRUCTIVE_MUTATION_APP = """
const AdminTable = () => {
  const [rows, setRows] = useState([{ id: 1, name: 'Avery' }]);
  const removeUser = (id) => setRows((prev) => prev.filter((row) => row.id !== id));
  return (
    <div>
      <header><h1>Admin Dashboard</h1></header>
      <nav aria-label="Admin nav"><a href="#">Overview</a></nav>
      <main>
        <table>
          <thead><tr><th>User</th><th>Actions</th></tr></thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{row.name}</td>
                <td><button onClick={() => removeUser(row.id)}>Delete user</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </main>
    </div>
  );
};
"""


class TestAdminDashboardScaffoldQuality:
    def _admin_plan(self, prompt: str = _ADMIN_GATE_PROMPT) -> Plan:
        plan = _plan()
        plan.user_message = prompt
        return plan

    def test_missing_admin_loading_error_states_is_flagged(self):
        issues = inspect_generated_scaffold_quality(
            [("src/App.tsx", _ADMIN_MISSING_STATES_APP)],
            plan=self._admin_plan(),
        )
        assert any(i.code == "admin_missing_loading_error_states" for i in issues)

    def test_admin_live_fetch_simulation_is_flagged(self):
        issues = inspect_generated_scaffold_quality(
            [("src/App.tsx", _ADMIN_ASYNC_FETCH_APP)],
            plan=self._admin_plan(),
        )
        assert any(i.code == "admin_live_fetch_impl_detected" for i in issues)

    def test_admin_destructive_live_mutation_is_flagged(self):
        issues = inspect_generated_scaffold_quality(
            [("src/App.tsx", _ADMIN_DESTRUCTIVE_MUTATION_APP)],
            plan=self._admin_plan(),
        )
        assert any(i.code == "admin_destructive_action_live_mutation" for i in issues)

    def test_admin_static_state_examples_and_semantics_are_accepted(self):
        issues = inspect_generated_scaffold_quality(
            [("src/App.tsx", _ADMIN_GOOD_STATES_TABLE_APP)],
            plan=self._admin_plan(),
        )
        assert not any(i.code.startswith("admin_") for i in issues)

    def test_admin_repair_prompt_requires_visible_static_state_examples(self):
        issues = [
            ScaffoldQualityIssue(
                code="admin_missing_loading_error_states",
                message="Missing empty/loading/error examples",
                path="src/App.tsx",
            )
        ]
        messages = build_scaffold_repair_prompt(
            self._admin_plan(),
            [("src/App.tsx", _ADMIN_MISSING_STATES_APP)],
            issues,
            base_system_prompt="BASE",
        )
        body = messages[0]["content"]
        assert "Admin dashboard repair focus" in body
        assert "visible static/local Empty / Loading / Error examples rendered in UI (not comments/text-only)" in body
        assert "'No users match this filter'" in body
        assert "'Loading admin preview example'" in body
        assert "'Unable to load local demo data'" in body

    def test_admin_repair_prompt_bans_live_fetch_and_api_loading_impl(self):
        issues = [
            ScaffoldQualityIssue(
                code="admin_live_fetch_impl_detected",
                message="Found fetch/useEffect/setTimeout API-style flow",
                path="src/App.tsx",
            )
        ]
        messages = build_scaffold_repair_prompt(
            self._admin_plan(),
            [("src/App.tsx", _ADMIN_ASYNC_FETCH_APP)],
            issues,
            base_system_prompt="BASE",
        )
        body = messages[0]["content"].lower()
        assert "never require fetch, async calls, api endpoints, backend, timers, polling, or live data" in body
        assert "do not use '/api', fetch(, axios, xmlhttprequest, async backend simulation, useeffect polling, or timer-based live loading" in body

    def test_admin_checks_not_applied_to_non_admin_prompt(self):
        plan = _plan()
        plan.user_message = "Build a card battle game with draw/discard loop."
        issues = inspect_generated_scaffold_quality(
            [("src/App.tsx", _ADMIN_MISSING_STATES_APP)],
            plan=plan,
        )
        assert not any(i.code.startswith("admin_") for i in issues)


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

    def test_repair_prompt_adds_tactics_focus_when_tactics_issue_present(self):
        issues = [
            ScaffoldQualityIssue(
                code="tactics_seed_not_applied",
                message="init not applied",
                path="src/Game.tsx",
            ),
            ScaffoldQualityIssue(
                code="tactics_enemy_turn_not_wired",
                message="enemy turn missing",
                path="src/gameReducer.ts",
            ),
        ]
        plan = _plan()
        plan.user_message = _TACTICS_GATE_PROMPT
        messages = build_scaffold_repair_prompt(
            plan,
            [("src/Game.tsx", _TACTICS_SHELL_GAME)],
            issues,
            base_system_prompt="BASE",
        )
        body = messages[0]["content"]
        assert "Turn-based tactics repair focus" in body
        assert "player and enemy units" in body.lower()
        assert "enemy turn" in body.lower()
        assert "movement range" in body.lower()
        assert "restart/new battle" in body.lower()
        assert "select/select_unit" in body.lower() or "select_unit" in body.lower()
        assert "attack/attack_unit" in body.lower() or "attack_unit" in body.lower()
        assert "enemy-turn range logic alone is insufficient" in body.lower()
        assert "immutably" in body.lower()
        assert "init/reset must not be no-op" in body.lower()

    def test_repair_prompt_adds_city_builder_focus_when_city_builder_issue_present(self):
        issues = [
            ScaffoldQualityIssue(
                code="city_missing_building_palette",
                message="no palette",
                path="src/App.tsx",
            ),
            ScaffoldQualityIssue(
                code="city_goal_not_wired",
                message="no population goal",
                path="src/App.tsx",
            ),
        ]
        plan = _plan()
        plan.user_message = _CITY_BUILDER_GATE_PROMPT
        messages = build_scaffold_repair_prompt(
            plan,
            [("src/App.tsx", _CITY_SHELL_APP)],
            issues,
            base_system_prompt="BASE",
        )
        body = messages[0]["content"]
        assert "City-builder repair focus" in body
        assert "valid JSON" in body
        assert "building palette" in body.lower()
        assert "occupied grid cells" in body.lower()
        assert "count placed farms" in body.lower() or "grid state" in body.lower()
        assert "happiness" in body.lower()
        assert "restart" in body.lower() or "new city" in body.lower()

    def test_repair_prompt_adds_happiness_derivation_focus(self):
        issues = [
            ScaffoldQualityIssue(
                code="city_happiness_not_wired",
                message="hardcoded happiness",
                path="src/state/cityState.tsx",
            ),
        ]
        plan = _plan()
        plan.user_message = _CITY_BUILDER_GATE_PROMPT
        messages = build_scaffold_repair_prompt(
            plan,
            [("src/state/cityState.tsx", _CITY_HAPPINESS_HARDCODED_ONE)],
            issues,
            base_system_prompt="BASE",
        )
        body = messages[0]["content"]
        assert "City-builder happiness repair focus" in body
        assert "hardcoded happiness" in body.lower() or "happinessChange = 1" in body
        assert "derive" in body.lower() or "derived" in body.lower()
        assert "wells/power" in body.lower() or "wells" in body.lower()
        assert "valid JSON" in body or "json/file_changes" in body.lower()


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

    def test_generate_scaffold_saas_triggers_escalated_second_repair_pass(self, monkeypatch):
        from src.ham.builder_llm_scaffold import ScaffoldResult, generate_scaffold

        first_pass_bad = json.dumps(
            {
                "file_changes": [
                    {"path": "src/App.tsx", "content": _SAAS_ASYNC_FETCH_APP},
                    {"path": "package.json", "content": "{}"},
                ],
                "assertions": ["renders"],
            }
        )
        second_pass_good = json.dumps(
            {
                "file_changes": [
                    {"path": "src/App.tsx", "content": _SAAS_GOOD_STATES_AND_TABLE_APP},
                    {"path": "package.json", "content": "{}"},
                ],
                "assertions": ["renders"],
            }
        )

        calls: list[str] = []

        def _complete_chat(messages, **_k):
            calls.append(messages[0]["content"])
            if len(calls) == 1:
                return first_pass_bad
            if len(calls) == 2:
                return first_pass_bad
            return second_pass_good

        plan = _plan()
        plan.user_message = _SAAS_GATE_PROMPT

        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test",
        )
        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.complete_chat_messages_openrouter",
            _complete_chat,
        )
        result = generate_scaffold(plan, project_id="p", workspace_id="w")
        assert isinstance(result, ScaffoldResult)
        assert len(calls) == 3
        assert "SaaS enforcement (must satisfy all):" in calls[2]

    def test_generate_scaffold_saas_applies_deterministic_fallback_when_repairs_still_fail(
        self, monkeypatch
    ):
        from src.ham.builder_llm_scaffold import ScaffoldResult, generate_scaffold

        bad_json = json.dumps(
            {
                "file_changes": [
                    {"path": "src/App.tsx", "content": _SAAS_ASYNC_FETCH_APP},
                    {"path": "package.json", "content": "{}"},
                ],
                "assertions": ["renders"],
            }
        )
        calls: list[str] = []

        def _complete_chat(messages, **_k):
            calls.append(messages[0]["content"])
            return bad_json

        plan = _plan()
        plan.user_message = _SAAS_GATE_PROMPT

        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test",
        )
        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.complete_chat_messages_openrouter",
            _complete_chat,
        )
        result = generate_scaffold(plan, project_id="p", workspace_id="w")
        assert isinstance(result, ScaffoldResult)
        assert len(calls) == 3
        app_content = dict(result.file_changes).get("src/App.tsx", "").lower()
        assert "<table" in app_content
        assert "no projects yet" in app_content
        assert "loading preview example" in app_content
        assert "unable to load local sample" in app_content
        assert "fetch(" not in app_content
        assert "useeffect(" not in app_content
        issues = inspect_generated_scaffold_quality(result.file_changes, plan=plan)
        assert not any(i.code.startswith("saas_") for i in issues)

    def test_generate_scaffold_admin_triggers_escalated_second_repair_pass(self, monkeypatch):
        from src.ham.builder_llm_scaffold import ScaffoldResult, generate_scaffold

        first_pass_bad = json.dumps(
            {
                "file_changes": [
                    {"path": "src/App.tsx", "content": _ADMIN_ASYNC_FETCH_APP},
                    {"path": "package.json", "content": "{}"},
                ],
                "assertions": ["renders"],
            }
        )
        second_pass_good = json.dumps(
            {
                "file_changes": [
                    {"path": "src/App.tsx", "content": _ADMIN_GOOD_STATES_TABLE_APP},
                    {"path": "package.json", "content": "{}"},
                ],
                "assertions": ["renders"],
            }
        )
        calls: list[str] = []

        def _complete_chat(messages, **_k):
            calls.append(messages[0]["content"])
            if len(calls) == 1:
                return first_pass_bad
            if len(calls) == 2:
                return first_pass_bad
            return second_pass_good

        plan = _plan()
        plan.user_message = _ADMIN_GATE_PROMPT

        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test",
        )
        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.complete_chat_messages_openrouter",
            _complete_chat,
        )
        result = generate_scaffold(plan, project_id="p", workspace_id="w")
        assert isinstance(result, ScaffoldResult)
        assert len(calls) == 3
        assert "Admin enforcement (must satisfy all):" in calls[2]

    def test_generate_scaffold_admin_applies_deterministic_fallback_when_repairs_still_fail(
        self, monkeypatch
    ):
        from src.ham.builder_llm_scaffold import ScaffoldResult, generate_scaffold

        bad_json = json.dumps(
            {
                "file_changes": [
                    {"path": "src/App.tsx", "content": _ADMIN_ASYNC_FETCH_APP},
                    {"path": "package.json", "content": "{}"},
                ],
                "assertions": ["renders"],
            }
        )
        calls: list[str] = []

        def _complete_chat(messages, **_k):
            calls.append(messages[0]["content"])
            return bad_json

        plan = _plan()
        plan.user_message = _ADMIN_GATE_PROMPT

        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.resolve_openrouter_api_key_for_actor",
            lambda ham_actor=None: "sk-or-test",
        )
        monkeypatch.setattr(
            "src.ham.builder_llm_scaffold.complete_chat_messages_openrouter",
            _complete_chat,
        )
        result = generate_scaffold(plan, project_id="p", workspace_id="w")
        assert isinstance(result, ScaffoldResult)
        assert len(calls) == 3
        app_content = dict(result.file_changes).get("src/App.tsx", "").lower()
        assert "admin dashboard (static demo)" in app_content
        assert "no users match this filter" in app_content
        assert "loading admin preview example" in app_content
        assert "unable to load local demo data" in app_content
        assert "<table" in app_content
        assert "<nav" in app_content
        assert "<main" in app_content
        assert "fetch(" not in app_content
        assert "useeffect(" not in app_content
        issues = inspect_generated_scaffold_quality(result.file_changes, plan=plan)
        assert not any(i.code.startswith("admin_") for i in issues)
