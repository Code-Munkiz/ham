"""Deterministic chat-triggered builder scaffold (no LLM codegen)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

from src.ham.builder_chat_intent import classify_builder_chat_intent
from src.persistence.builder_source_store import (
    ImportJob,
    ProjectSource,
    SourceSnapshot,
    get_builder_source_store,
)

_MANIFEST_KIND_INLINE = "inline_text_bundle"
_MAX_TOTAL_TEXT = 200_000
_MAX_FILE_BYTES = 60_000
_MAX_FILES = 24


def _sanitize_title(user_plain: str) -> str:
    words = re.sub(r"[^\w\s-]", " ", user_plain, flags=re.UNICODE).split()
    title = " ".join(words[:12]).strip()
    if not title:
        return "HAM Builder App"
    return title[:120]


def _is_tetris_prompt(user_plain: str) -> bool:
    lowered = str(user_plain or "").strip().lower()
    return "tetris" in lowered


def _build_tetris_scaffold_files(*, title: str, safe_pkg: str) -> dict[str, str]:
    return {
        "package.json": json.dumps(
            {
                "name": safe_pkg,
                "private": True,
                "version": "0.0.1",
                "type": "module",
                "scripts": {
                    "dev": "vite",
                    "build": "vite build",
                    "preview": "vite preview",
                },
                "dependencies": {"react": "^18.3.1", "react-dom": "^18.3.1"},
                "devDependencies": {
                    "@vitejs/plugin-react": "^4.3.4",
                    "typescript": "^5.6.3",
                    "vite": "^5.4.11",
                },
            },
            indent=2,
        )
        + "\n",
        "index.html": (
            "<!doctype html>\n"
            '<html lang="en">\n'
            "  <head>\n"
            '    <meta charset="UTF-8" />\n'
            f"    <title>{title}</title>\n"
            '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
            "  </head>\n"
            "  <body>\n"
            '    <div id="root"></div>\n'
            '    <script type="module" src="/src/main.tsx"></script>\n'
            "  </body>\n"
            "</html>\n"
        ),
        "src/main.tsx": (
            "import React from \"react\";\n"
            "import ReactDOM from \"react-dom/client\";\n"
            "import App from \"./App\";\n"
            "import \"./styles.css\";\n"
            "ReactDOM.createRoot(document.getElementById(\"root\")!).render(\n"
            "  <React.StrictMode>\n"
            "    <App />\n"
            "  </React.StrictMode>,\n"
            ");\n"
        ),
        "vite.config.ts": (
            "import { defineConfig } from \"vite\";\n"
            "import react from \"@vitejs/plugin-react\";\n"
            "\n"
            "export default defineConfig({\n"
            "  plugins: [react()],\n"
            "  server: {\n"
            "    hmr: false,\n"
            "  },\n"
            "});\n"
        ),
        "src/App.tsx": (
            "import React, { useCallback, useEffect, useMemo, useState } from \"react\";\n"
            "\n"
            "type Cell = 0 | string;\n"
            "type Board = Cell[][];\n"
            "type Coord = { x: number; y: number };\n"
            "type PieceType = \"I\" | \"O\" | \"T\" | \"S\" | \"Z\" | \"J\" | \"L\";\n"
            "type ActivePiece = { type: PieceType; matrix: number[][]; color: string; pos: Coord };\n"
            "\n"
            "const BOARD_WIDTH = 10;\n"
            "const BOARD_HEIGHT = 20;\n"
            "const BASE_TICK_MS = 700;\n"
            "const MIN_TICK_MS = 110;\n"
            "\n"
            "const PIECES: Record<PieceType, { matrix: number[][]; color: string }> = {\n"
            "  I: { matrix: [[1, 1, 1, 1]], color: \"c-cyan\" },\n"
            "  O: { matrix: [[1, 1], [1, 1]], color: \"c-yellow\" },\n"
            "  T: { matrix: [[0, 1, 0], [1, 1, 1]], color: \"c-purple\" },\n"
            "  S: { matrix: [[0, 1, 1], [1, 1, 0]], color: \"c-green\" },\n"
            "  Z: { matrix: [[1, 1, 0], [0, 1, 1]], color: \"c-red\" },\n"
            "  J: { matrix: [[1, 0, 0], [1, 1, 1]], color: \"c-blue\" },\n"
            "  L: { matrix: [[0, 0, 1], [1, 1, 1]], color: \"c-orange\" },\n"
            "};\n"
            "\n"
            "function emptyBoard(): Board {\n"
            "  return Array.from({ length: BOARD_HEIGHT }, () => Array.from({ length: BOARD_WIDTH }, () => 0 as Cell));\n"
            "}\n"
            "\n"
            "function cloneMatrix(matrix: number[][]): number[][] {\n"
            "  return matrix.map((row) => [...row]);\n"
            "}\n"
            "\n"
            "function rotateMatrix(matrix: number[][]): number[][] {\n"
            "  const h = matrix.length;\n"
            "  const w = matrix[0]?.length || 0;\n"
            "  const out = Array.from({ length: w }, () => Array.from({ length: h }, () => 0));\n"
            "  for (let y = 0; y < h; y += 1) {\n"
            "    for (let x = 0; x < w; x += 1) {\n"
            "      out[x][h - 1 - y] = matrix[y][x];\n"
            "    }\n"
            "  }\n"
            "  return out;\n"
            "}\n"
            "\n"
            "function randomPieceType(): PieceType {\n"
            "  const keys = Object.keys(PIECES) as PieceType[];\n"
            "  return keys[Math.floor(Math.random() * keys.length)] || \"T\";\n"
            "}\n"
            "\n"
            "function makePiece(type: PieceType): ActivePiece {\n"
            "  const base = PIECES[type];\n"
            "  return {\n"
            "    type,\n"
            "    matrix: cloneMatrix(base.matrix),\n"
            "    color: base.color,\n"
            "    pos: { x: Math.floor((BOARD_WIDTH - base.matrix[0].length) / 2), y: 0 },\n"
            "  };\n"
            "}\n"
            "\n"
            "function collides(board: Board, piece: ActivePiece): boolean {\n"
            "  for (let y = 0; y < piece.matrix.length; y += 1) {\n"
            "    for (let x = 0; x < piece.matrix[y].length; x += 1) {\n"
            "      if (!piece.matrix[y][x]) continue;\n"
            "      const bx = piece.pos.x + x;\n"
            "      const by = piece.pos.y + y;\n"
            "      if (bx < 0 || bx >= BOARD_WIDTH || by >= BOARD_HEIGHT) return true;\n"
            "      if (by >= 0 && board[by][bx]) return true;\n"
            "    }\n"
            "  }\n"
            "  return false;\n"
            "}\n"
            "\n"
            "function mergePiece(board: Board, piece: ActivePiece): Board {\n"
            "  const next = board.map((row) => [...row]);\n"
            "  for (let y = 0; y < piece.matrix.length; y += 1) {\n"
            "    for (let x = 0; x < piece.matrix[y].length; x += 1) {\n"
            "      if (!piece.matrix[y][x]) continue;\n"
            "      const bx = piece.pos.x + x;\n"
            "      const by = piece.pos.y + y;\n"
            "      if (by >= 0 && by < BOARD_HEIGHT && bx >= 0 && bx < BOARD_WIDTH) {\n"
            "        next[by][bx] = piece.color;\n"
            "      }\n"
            "    }\n"
            "  }\n"
            "  return next;\n"
            "}\n"
            "\n"
            "function clearLines(board: Board): { board: Board; cleared: number } {\n"
            "  const kept = board.filter((row) => row.some((cell) => cell === 0));\n"
            "  const cleared = BOARD_HEIGHT - kept.length;\n"
            "  const fill = Array.from({ length: cleared }, () => Array.from({ length: BOARD_WIDTH }, () => 0 as Cell));\n"
            "  return { board: [...fill, ...kept], cleared };\n"
            "}\n"
            "\n"
            "function projectBoard(board: Board, piece: ActivePiece | null): Board {\n"
            "  if (!piece) return board;\n"
            "  const out = board.map((row) => [...row]);\n"
            "  for (let y = 0; y < piece.matrix.length; y += 1) {\n"
            "    for (let x = 0; x < piece.matrix[y].length; x += 1) {\n"
            "      if (!piece.matrix[y][x]) continue;\n"
            "      const bx = piece.pos.x + x;\n"
            "      const by = piece.pos.y + y;\n"
            "      if (by >= 0 && by < BOARD_HEIGHT && bx >= 0 && bx < BOARD_WIDTH) {\n"
            "        out[by][bx] = piece.color;\n"
            "      }\n"
            "    }\n"
            "  }\n"
            "  return out;\n"
            "}\n"
            "\n"
            "export default function App() {\n"
            "  const [board, setBoard] = useState<Board>(() => emptyBoard());\n"
            "  const [active, setActive] = useState<ActivePiece | null>(() => makePiece(randomPieceType()));\n"
            "  const [nextType, setNextType] = useState<PieceType>(() => randomPieceType());\n"
            "  const [holdType, setHoldType] = useState<PieceType | null>(null);\n"
            "  const [canHold, setCanHold] = useState(true);\n"
            "  const [score, setScore] = useState(0);\n"
            "  const [lines, setLines] = useState(0);\n"
            "  const [level, setLevel] = useState(1);\n"
            "  const [gameOver, setGameOver] = useState(false);\n"
            "  const [muted, setMuted] = useState(false);\n"
            "\n"
            "  const tickMs = useMemo(() => Math.max(MIN_TICK_MS, BASE_TICK_MS - (level - 1) * 60), [level]);\n"
            "\n"
            "  const spawnNext = useCallback((baseBoard: Board) => {\n"
            "    const candidate = makePiece(nextType);\n"
            "    const upcoming = randomPieceType();\n"
            "    if (collides(baseBoard, candidate)) {\n"
            "      setGameOver(true);\n"
            "      setActive(null);\n"
            "      return;\n"
            "    }\n"
            "    setActive(candidate);\n"
            "    setNextType(upcoming);\n"
            "    setCanHold(true);\n"
            "  }, [nextType]);\n"
            "\n"
            "  const lockAndAdvance = useCallback((piece: ActivePiece) => {\n"
            "    const merged = mergePiece(board, piece);\n"
            "    const { board: clearedBoard, cleared } = clearLines(merged);\n"
            "    if (cleared > 0) {\n"
            "      setScore((s) => s + cleared * 100 * Math.max(1, level));\n"
            "      setLines((l) => {\n"
            "        const total = l + cleared;\n"
            "        setLevel(Math.floor(total / 10) + 1);\n"
            "        return total;\n"
            "      });\n"
            "    }\n"
            "    setBoard(clearedBoard);\n"
            "    spawnNext(clearedBoard);\n"
            "  }, [board, level, spawnNext]);\n"
            "\n"
            "  const move = useCallback((dx: number, dy: number): boolean => {\n"
            "    if (!active || gameOver) return false;\n"
            "    const moved: ActivePiece = { ...active, pos: { x: active.pos.x + dx, y: active.pos.y + dy } };\n"
            "    if (collides(board, moved)) {\n"
            "      if (dy > 0) {\n"
            "        lockAndAdvance(active);\n"
            "      }\n"
            "      return false;\n"
            "    }\n"
            "    setActive(moved);\n"
            "    return true;\n"
            "  }, [active, board, gameOver, lockAndAdvance]);\n"
            "\n"
            "  const rotate = useCallback(() => {\n"
            "    if (!active || gameOver) return;\n"
            "    const rotated: ActivePiece = { ...active, matrix: rotateMatrix(active.matrix) };\n"
            "    const kicks = [0, -1, 1, -2, 2];\n"
            "    for (const kick of kicks) {\n"
            "      const candidate: ActivePiece = { ...rotated, pos: { x: active.pos.x + kick, y: active.pos.y } };\n"
            "      if (!collides(board, candidate)) {\n"
            "        setActive(candidate);\n"
            "        return;\n"
            "      }\n"
            "    }\n"
            "  }, [active, board, gameOver]);\n"
            "\n"
            "  const hardDrop = useCallback(() => {\n"
            "    if (!active || gameOver) return;\n"
            "    let candidate = active;\n"
            "    while (!collides(board, { ...candidate, pos: { x: candidate.pos.x, y: candidate.pos.y + 1 } })) {\n"
            "      candidate = { ...candidate, pos: { x: candidate.pos.x, y: candidate.pos.y + 1 } };\n"
            "    }\n"
            "    setActive(candidate);\n"
            "    lockAndAdvance(candidate);\n"
            "  }, [active, board, gameOver, lockAndAdvance]);\n"
            "\n"
            "  const hold = useCallback(() => {\n"
            "    if (!active || gameOver || !canHold) return;\n"
            "    const currentType = active.type;\n"
            "    if (holdType) {\n"
            "      const replacement = makePiece(holdType);\n"
            "      if (collides(board, replacement)) {\n"
            "        setGameOver(true);\n"
            "        setActive(null);\n"
            "        return;\n"
            "      }\n"
            "      setActive(replacement);\n"
            "      setHoldType(currentType);\n"
            "    } else {\n"
            "      setHoldType(currentType);\n"
            "      spawnNext(board);\n"
            "    }\n"
            "    setCanHold(false);\n"
            "  }, [active, board, canHold, gameOver, holdType, spawnNext]);\n"
            "\n"
            "  const restart = useCallback(() => {\n"
            "    setBoard(emptyBoard());\n"
            "    setActive(makePiece(randomPieceType()));\n"
            "    setNextType(randomPieceType());\n"
            "    setHoldType(null);\n"
            "    setCanHold(true);\n"
            "    setScore(0);\n"
            "    setLines(0);\n"
            "    setLevel(1);\n"
            "    setGameOver(false);\n"
            "  }, []);\n"
            "\n"
            "  useEffect(() => {\n"
            "    if (gameOver || !active) return;\n"
            "    const timer = window.setInterval(() => {\n"
            "      move(0, 1);\n"
            "    }, tickMs);\n"
            "    return () => window.clearInterval(timer);\n"
            "  }, [active, gameOver, move, tickMs]);\n"
            "\n"
            "  useEffect(() => {\n"
            "    const onKey = (event: KeyboardEvent) => {\n"
            "      if (event.key === \"ArrowLeft\") {\n"
            "        event.preventDefault();\n"
            "        move(-1, 0);\n"
            "      } else if (event.key === \"ArrowRight\") {\n"
            "        event.preventDefault();\n"
            "        move(1, 0);\n"
            "      } else if (event.key === \"ArrowDown\") {\n"
            "        event.preventDefault();\n"
            "        move(0, 1);\n"
            "      } else if (event.key === \"ArrowUp\" || event.key.toLowerCase() === \"x\") {\n"
            "        event.preventDefault();\n"
            "        rotate();\n"
            "      } else if (event.key === \" \") {\n"
            "        event.preventDefault();\n"
            "        hardDrop();\n"
            "      } else if (event.key.toLowerCase() === \"c\") {\n"
            "        event.preventDefault();\n"
            "        hold();\n"
            "      } else if (event.key.toLowerCase() === \"r\") {\n"
            "        event.preventDefault();\n"
            "        restart();\n"
            "      } else if (event.key.toLowerCase() === \"m\") {\n"
            "        setMuted((m) => !m);\n"
            "      }\n"
            "    };\n"
            "    window.addEventListener(\"keydown\", onKey);\n"
            "    return () => window.removeEventListener(\"keydown\", onKey);\n"
            "  }, [hardDrop, hold, move, restart, rotate]);\n"
            "\n"
            "  const renderedBoard = useMemo(() => projectBoard(board, active), [active, board]);\n"
            "\n"
            "  return (\n"
            "    <main className=\"app-shell\">\n"
            "      <header className=\"top-bar\">\n"
            f"        <h1>{title}</h1>\n"
            "        <p>Playable preview generated by HAM.</p>\n"
            "      </header>\n"
            "      <section className=\"game-layout\">\n"
            "        <aside className=\"panel\">\n"
            "          <h2>Stats</h2>\n"
            "          <dl>\n"
            "            <div><dt>Score</dt><dd>{score}</dd></div>\n"
            "            <div><dt>Lines</dt><dd>{lines}</dd></div>\n"
            "            <div><dt>Level</dt><dd>{level}</dd></div>\n"
            "            <div><dt>Sound</dt><dd>{muted ? \"Muted\" : \"On\"}</dd></div>\n"
            "          </dl>\n"
            "          <button type=\"button\" onClick={restart}>Restart</button>\n"
            "        </aside>\n"
            "        <section className=\"board-wrap\" aria-label=\"Tetris board\">\n"
            "          <div className=\"board\">\n"
            "            {renderedBoard.map((row, y) =>\n"
            "              row.map((cell, x) => (\n"
            "                <span key={`${y}-${x}`} className={`cell ${cell ? String(cell) : \"\"}`} />\n"
            "              )),\n"
            "            )}\n"
            "          </div>\n"
            "          {gameOver ? <div className=\"game-over\">Game Over</div> : null}\n"
            "        </section>\n"
            "        <aside className=\"panel\">\n"
            "          <h2>Queue</h2>\n"
            "          <p>Next: {nextType}</p>\n"
            "          <p>Hold: {holdType || \"-\"}</p>\n"
            "          <h2>Controls</h2>\n"
            "          <ul>\n"
            "            <li>Arrow keys: Move</li>\n"
            "            <li>Up / X: Rotate</li>\n"
            "            <li>Space: Hard drop</li>\n"
            "            <li>C: Hold piece</li>\n"
            "            <li>R: Restart</li>\n"
            "            <li>M: Toggle sound</li>\n"
            "          </ul>\n"
            "        </aside>\n"
            "      </section>\n"
            "    </main>\n"
            "  );\n"
            "}\n"
        ),
        "src/styles.css": (
            ":root {\n"
            "  color-scheme: dark;\n"
            "  font-family: Inter, Segoe UI, sans-serif;\n"
            "  background: radial-gradient(circle at top, #0b1530 0%, #040711 45%, #020308 100%);\n"
            "  color: #ebf5ff;\n"
            "}\n"
            "body {\n"
            "  margin: 0;\n"
            "  min-height: 100vh;\n"
            "}\n"
            ".app-shell {\n"
            "  max-width: 1080px;\n"
            "  margin: 0 auto;\n"
            "  padding: 1.25rem;\n"
            "}\n"
            ".top-bar {\n"
            "  margin-bottom: 1rem;\n"
            "}\n"
            ".top-bar h1 {\n"
            "  margin: 0;\n"
            "  font-size: 1.4rem;\n"
            "}\n"
            ".top-bar p {\n"
            "  margin: 0.35rem 0 0;\n"
            "  color: #9bc4ff;\n"
            "}\n"
            ".game-layout {\n"
            "  display: grid;\n"
            "  grid-template-columns: 220px 1fr 220px;\n"
            "  gap: 0.8rem;\n"
            "}\n"
            ".panel {\n"
            "  border: 1px solid #18325f;\n"
            "  border-radius: 12px;\n"
            "  background: rgba(5, 12, 28, 0.78);\n"
            "  padding: 0.85rem;\n"
            "  backdrop-filter: blur(5px);\n"
            "}\n"
            ".panel h2 {\n"
            "  margin: 0 0 0.45rem;\n"
            "  font-size: 0.85rem;\n"
            "  text-transform: uppercase;\n"
            "  letter-spacing: 0.05em;\n"
            "  color: #95bdff;\n"
            "}\n"
            ".panel dl {\n"
            "  margin: 0 0 0.75rem;\n"
            "}\n"
            ".panel dl div {\n"
            "  display: flex;\n"
            "  justify-content: space-between;\n"
            "  margin-bottom: 0.3rem;\n"
            "}\n"
            ".panel ul {\n"
            "  margin: 0;\n"
            "  padding-left: 1rem;\n"
            "  color: #c5dbff;\n"
            "}\n"
            ".panel button {\n"
            "  width: 100%;\n"
            "  border: 1px solid #2d6ae0;\n"
            "  background: linear-gradient(180deg, #2d6ae0 0%, #214ea6 100%);\n"
            "  color: #f7fbff;\n"
            "  border-radius: 8px;\n"
            "  padding: 0.45rem 0.6rem;\n"
            "  cursor: pointer;\n"
            "}\n"
            ".board-wrap {\n"
            "  position: relative;\n"
            "  border: 1px solid #14305d;\n"
            "  border-radius: 12px;\n"
            "  background: rgba(3, 10, 22, 0.92);\n"
            "  padding: 0.5rem;\n"
            "}\n"
            ".board {\n"
            "  display: grid;\n"
            "  grid-template-columns: repeat(10, minmax(20px, 1fr));\n"
            "  gap: 2px;\n"
            "}\n"
            ".cell {\n"
            "  width: 100%;\n"
            "  aspect-ratio: 1;\n"
            "  border-radius: 2px;\n"
            "  background: rgba(20, 44, 88, 0.36);\n"
            "}\n"
            ".c-cyan { background: #11d7f8; }\n"
            ".c-yellow { background: #ffd84d; }\n"
            ".c-purple { background: #ad6dff; }\n"
            ".c-green { background: #3df28f; }\n"
            ".c-red { background: #ff6584; }\n"
            ".c-blue { background: #5796ff; }\n"
            ".c-orange { background: #ffa53a; }\n"
            ".game-over {\n"
            "  position: absolute;\n"
            "  inset: 0;\n"
            "  display: grid;\n"
            "  place-items: center;\n"
            "  font-size: 1.15rem;\n"
            "  font-weight: 700;\n"
            "  color: #ff8ca2;\n"
            "  background: rgba(2, 5, 14, 0.72);\n"
            "}\n"
            "@media (max-width: 960px) {\n"
            "  .game-layout {\n"
            "    grid-template-columns: 1fr;\n"
            "  }\n"
            "}\n"
        ),
        "README.md": (
            f"# {title}\n\n"
            "This project is generated by HAM from a Tetris-style build request.\n\n"
            "## Included gameplay\n\n"
            "- Falling tetromino pieces on a 10x20 board\n"
            "- Move, rotate, soft drop, hard drop\n"
            "- Hold and next piece indicators\n"
            "- Line clear scoring, levels, and game over + restart\n\n"
            "## Controls\n\n"
            "- Arrow Left / Right: move\n"
            "- Arrow Down: soft drop\n"
            "- Arrow Up or X: rotate\n"
            "- Space: hard drop\n"
            "- C: hold\n"
            "- R: restart\n"
            "- M: mute toggle\n"
        ),
    }


def _build_react_scaffold_files(user_plain: str) -> dict[str, str]:
    title = _sanitize_title(user_plain)
    safe_pkg = re.sub(r"[^a-z0-9-]", "-", title.lower())[:40].strip("-") or "ham-builder-app"
    if _is_tetris_prompt(user_plain):
        return _build_tetris_scaffold_files(title=title, safe_pkg=safe_pkg)
    return {
        "package.json": json.dumps(
            {
                "name": safe_pkg,
                "private": True,
                "version": "0.0.1",
                "type": "module",
                "scripts": {
                    "dev": "vite",
                    "build": "vite build",
                    "preview": "vite preview",
                },
                "dependencies": {"react": "^18.3.1", "react-dom": "^18.3.1"},
                "devDependencies": {
                    "@vitejs/plugin-react": "^4.3.4",
                    "typescript": "^5.6.3",
                    "vite": "^5.4.11",
                },
            },
            indent=2,
        )
        + "\n",
        "index.html": (
            "<!doctype html>\n"
            '<html lang="en">\n'
            "  <head>\n"
            '    <meta charset="UTF-8" />\n'
            f"    <title>{title}</title>\n"
            '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
            "  </head>\n"
            "  <body>\n"
            '    <div id="root"></div>\n'
            '    <script type="module" src="/src/main.tsx"></script>\n'
            "  </body>\n"
            "</html>\n"
        ),
        "src/main.tsx": (
            "import React from \"react\";\n"
            "import ReactDOM from \"react-dom/client\";\n"
            "import App from \"./App\";\n"
            "import \"./styles.css\";\n"
            "ReactDOM.createRoot(document.getElementById(\"root\")!).render(\n"
            "  <React.StrictMode>\n"
            "    <App />\n"
            "  </React.StrictMode>,\n"
            ");\n"
        ),
        "src/App.tsx": (
            "import React from \"react\";\n"
            "export default function App() {\n"
            f"  return (\n"
            f"    <main className=\"app-shell\">\n"
            f"      <h1>{title}</h1>\n"
            "      <p className=\"muted\">\n"
            "        Scaffold created from your chat request. HAM will attach a cloud preview when the preview\n"
            "        environment is ready. Use the Code tab to browse source files.\n"
            "      </p>\n"
            "      <p className=\"muted developer-hint\">\n"
            "        Developer: you may run <code>npm install</code> and <code>npm run dev</code> locally if needed.\n"
            "      </p>\n"
            "    </main>\n"
            "  );\n"
            "}\n"
        ),
        "src/styles.css": (
            ":root {\n"
            "  font-family: system-ui, sans-serif;\n"
            "  color: #e8eef8;\n"
            "  background: #040d14;\n"
            "}\n"
            ".app-shell {\n"
            "  max-width: 720px;\n"
            "  margin: 3rem auto;\n"
            "  padding: 0 1.5rem;\n"
            "}\n"
            ".muted {\n"
            "  color: rgba(232, 238, 248, 0.72);\n"
            "  line-height: 1.5;\n"
            "}\n"
        ),
        "README.md": (
            f"# {title}\n\n"
            "This is a small Vite + React scaffold produced by HAM chat.\n\n"
            "- **Preview:** HAM attaches a cloud preview when the preview environment is ready (see the Workbench Preview tab).\n"
            "- **Code:** Source files are listed under the Workbench Code tab.\n\n"
            "### Developer (optional)\n\n"
            "For local debugging you can run `npm install` and `npm run dev` on your machine.\n"
        ),
    }


def _bounded_files(user_plain: str) -> dict[str, str]:
    raw = _build_react_scaffold_files(user_plain)
    if len(raw) > _MAX_FILES:
        raise ValueError("too_many_files")
    out: dict[str, str] = {}
    total = 0
    for rel, text in raw.items():
        norm = rel.replace("\\", "/").lstrip("/")
        if not norm or ".." in norm.split("/"):
            continue
        body = text if isinstance(text, str) else str(text)
        if len(body.encode("utf-8")) > _MAX_FILE_BYTES:
            body = body.encode("utf-8")[:_MAX_FILE_BYTES].decode("utf-8", errors="ignore")
        total += len(body)
        if total > _MAX_TOTAL_TEXT:
            raise ValueError("bundle_too_large")
        out[norm] = body
    return out


def _fingerprint(session_id: str, user_plain: str) -> str:
    payload = f"{session_id}\n{user_plain.strip()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def materialize_inline_files_as_zip_artifact(
    *,
    workspace_id: str,
    project_id: str,
    files: dict[str, str],
) -> tuple[str, int]:
    """Write a bounded ZIP to the builder artifact dir; return (builder-artifact:// URI, zip byte size)."""
    artifact_id = f"bzip_{uuid.uuid4().hex}"
    root = _artifact_root()
    target_dir = root / workspace_id / project_id
    target_dir.mkdir(parents=True, exist_ok=True)
    zip_path = target_dir / f"{artifact_id}.zip"
    buf = BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel, text in sorted(files.items()):
            norm = rel.replace("\\", "/").lstrip("/")
            if not norm or ".." in norm.split("/"):
                continue
            zf.writestr(norm, text.encode("utf-8"))
    payload = buf.getvalue()
    max_zip = 50 * 1024 * 1024
    if len(payload) > max_zip:
        raise ValueError("artifact_zip_too_large")
    zip_path.write_bytes(payload)
    return f"builder-artifact://{artifact_id}", len(payload)


def _existing_fingerprint_snapshot_id(
    *,
    workspace_id: str,
    project_id: str,
    fingerprint: str,
) -> str | None:
    store = get_builder_source_store()
    for snap in store.list_source_snapshots(workspace_id=workspace_id, project_id=project_id):
        meta = snap.metadata or {}
        if str(meta.get("chat_scaffold_fingerprint") or "") == fingerprint:
            return snap.id
    return None


def maybe_chat_scaffold_for_turn(
    *,
    workspace_id: str | None,
    project_id: str | None,
    session_id: str,
    last_user_plain: str,
    created_by: str,
) -> dict[str, Any] | None:
    """If eligible, create ProjectSource + snapshot + import job; return summary dict."""
    ws = (workspace_id or "").strip()
    pid = (project_id or "").strip()
    if not ws or not pid:
        return None
    if classify_builder_chat_intent(last_user_plain) != "build_or_create":
        return None
    fp = _fingerprint(session_id, last_user_plain)
    existing_snapshot_id = _existing_fingerprint_snapshot_id(
        workspace_id=ws,
        project_id=pid,
        fingerprint=fp,
    )
    if existing_snapshot_id:
        return {
            "builder_intent": "build_or_create",
            "scaffolded": False,
            "deduplicated": True,
            "source_snapshot_id": existing_snapshot_id,
        }

    files = _bounded_files(last_user_plain)
    entries_manifest: list[dict[str, Any]] = []
    total_bytes = 0
    for path, text in sorted(files.items()):
        b = text.encode("utf-8")
        total_bytes += len(b)
        entries_manifest.append(
            {
                "path": path,
                "size_bytes": len(b),
                "text": text,
            }
        )

    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode("utf-8")).hexdigest()
    artifact_uri, zip_size = materialize_inline_files_as_zip_artifact(
        workspace_id=ws,
        project_id=pid,
        files=files,
    )
    store = get_builder_source_store()

    job = store.create_import_job(
        workspace_id=ws,
        project_id=pid,
        created_by=created_by,
        phase="received",
        status="queued",
        metadata={
            "activity_title": "Builder request received",
            "activity_message": "Chat requested a new builder scaffold.",
            "origin": "chat_scaffold",
        },
    )
    job = store.mark_import_job_running(import_job_id=job.id, phase="scaffolding")
    job = store.upsert_import_job(
        job.model_copy(
            update={
                "metadata": {
                    **(job.metadata or {}),
                    "activity_title": "Preparing your project source",
                    "activity_message": "Creating initial files from your chat prompt.",
                },
            },
        ),
    )

    source = ProjectSource(
        workspace_id=ws,
        project_id=pid,
        kind="chat_scaffold",
        status="ready",
        display_name="Chat scaffold",
        origin_ref="ham_chat",
        created_by=created_by,
        metadata={"chat_scaffold": "1", "import_job_id": job.id},
    )
    source = store.upsert_project_source(source)

    snapshot = SourceSnapshot(
        workspace_id=ws,
        project_id=pid,
        project_source_id=source.id,
        digest_sha256=digest,
        size_bytes=zip_size,
        artifact_uri=artifact_uri,
        manifest={
            "kind": _MANIFEST_KIND_INLINE,
            "file_count": len(entries_manifest),
            "entries": [{"path": e["path"], "size_bytes": e["size_bytes"]} for e in entries_manifest],
            "inline_files": files,
        },
        created_by=created_by,
        metadata={
            "chat_scaffold": "1",
            "chat_scaffold_fingerprint": fp,
            "import_job_id": job.id,
        },
    )
    snapshot = store.upsert_source_snapshot(snapshot)
    source.active_snapshot_id = snapshot.id
    source = store.upsert_project_source(source)

    job_done = store.mark_import_job_succeeded(
        import_job_id=job.id,
        phase="materialized",
        source_snapshot_id=snapshot.id,
        stats={"file_count": len(files), "inline_bytes": total_bytes, "artifact_zip_bytes": zip_size},
    )
    job_done = store.upsert_import_job(
        job_done.model_copy(
            update={
                "metadata": {
                    **(job_done.metadata or {}),
                    "activity_title": "Code files ready",
                    "activity_message": "Workbench Code tab can list this snapshot.",
                },
            },
        ),
    )

    return {
        "builder_intent": "build_or_create",
        "scaffolded": True,
        "project_source_id": source.id,
        "source_snapshot_id": snapshot.id,
        "import_job_id": job_done.id,
    }


def read_inline_snapshot_file(*, snapshot: SourceSnapshot, rel_path: str) -> tuple[str, int] | None:
    """Return (utf-8 text, byte length) for an inline scaffold file, or None."""
    manifest = snapshot.manifest or {}
    if manifest.get("kind") != _MANIFEST_KIND_INLINE:
        return None
    raw_files = manifest.get("inline_files")
    if not isinstance(raw_files, dict):
        return None
    norm = rel_path.replace("\\", "/").lstrip("/")
    if ".." in norm.split("/"):
        return None
    text = raw_files.get(norm)
    if not isinstance(text, str):
        return None
    b = text.encode("utf-8")
    if len(b) > _MAX_FILE_BYTES:
        return None
    return text, len(b)


def read_zip_snapshot_file_bytes(*, zip_bytes: bytes, rel_path: str, max_out: int) -> bytes | None:
    norm = rel_path.replace("\\", "/").lstrip("/")
    if ".." in norm.split("/"):
        return None
    try:
        buf = BytesIO(zip_bytes)
        with zipfile.ZipFile(buf) as zf:
            info = zf.getinfo(norm)
            if info.is_dir():
                return None
            if info.file_size > max_out:
                return None
            data = zf.read(info)
            if len(data) > max_out:
                return None
            return data
    except (KeyError, OSError, zipfile.BadZipFile, RuntimeError):
        return None


def _artifact_root() -> Path:
    raw = (os.environ.get("HAM_BUILDER_SOURCE_ARTIFACT_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".ham" / "builder-source-artifacts").resolve()


def load_zip_bytes_for_snapshot(
    *,
    workspace_id: str,
    project_id: str,
    artifact_id: str,
) -> bytes | None:
    root = _artifact_root() / workspace_id / project_id
    path = root / f"{artifact_id}.zip"
    try:
        if path.is_file() and path.stat().st_size <= 50 * 1024 * 1024:
            return path.read_bytes()
    except OSError:
        return None
    return None
