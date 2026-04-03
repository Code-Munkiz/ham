"""
Regression tests for src/memory_heist.py — covers all 8 required cases.
"""
from __future__ import annotations

from unittest.mock import patch

from src.memory_heist import (
    INTERESTING_EXTENSIONS,
    MAX_DIFF_CHARS,
    Message,
    ProjectContext,
    SessionMemory,
    git_diff,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_session(*contents: str, role: str = "user") -> SessionMemory:
    s = SessionMemory()
    for c in contents:
        s.add(role, c)
    return s


# ---------------------------------------------------------------------------
# Test 1 — _extract_key_files: forward-slash, backslash, bare filename
# ---------------------------------------------------------------------------

class TestExtractKeyFiles:
    def _call(self, *contents: str) -> list[str]:
        msgs = [Message(role="user", content=c) for c in contents]
        return SessionMemory._extract_key_files(msgs)

    def test_forward_slash_path(self):
        result = self._call("edited src/memory_heist.py today")
        assert any("memory_heist.py" in f for f in result)

    def test_backslash_path(self):
        result = self._call(r"edited src\memory_heist.py today")
        assert any("memory_heist.py" in f for f in result)

    def test_bare_filename_with_interesting_extension(self):
        result = self._call("opened memory_heist.py in the editor")
        assert any("memory_heist.py" in f for f in result)

    def test_extension_not_interesting_is_excluded(self):
        result = self._call("binary file image.png is large")
        assert not any(".png" in f for f in result)

    def test_all_interesting_extensions_are_covered(self):
        # Spot-check a few from INTERESTING_EXTENSIONS
        for ext in (".py", ".ts", ".md", ".json"):
            assert ext in INTERESTING_EXTENSIONS


# ---------------------------------------------------------------------------
# Test 2 — _format_continuation: new closing text
# ---------------------------------------------------------------------------

def test_format_continuation_new_closing_text():
    text = SessionMemory._format_continuation("Summary: blah", has_preserved=False)
    assert "Continue executing the current task plan from where it left off." in text
    assert "Continue the conversation from where it left off" not in text


# ---------------------------------------------------------------------------
# Test 3 — _extract_prior_summary: parses continuation built with OLD closing text
# ---------------------------------------------------------------------------

def test_extract_prior_summary_old_closing_text():
    old_continuation = (
        "This session is being continued from a previous conversation "
        "that ran out of context. The summary below covers the earlier "
        "portion of the conversation.\n\n"
        "Summary: did some work\n"
        "\nContinue the conversation from where it left off without "
        "asking the user any further questions."
    )
    s = SessionMemory()
    s.messages.append(Message(role="system", content=old_continuation))
    result = s._extract_prior_summary()
    assert result is not None
    assert "did some work" in result
    # Closing text must be stripped
    assert "Continue the conversation" not in result


# ---------------------------------------------------------------------------
# Test 4 — _extract_prior_summary: parses continuation built with NEW closing text
# ---------------------------------------------------------------------------

def test_extract_prior_summary_new_closing_text():
    s = SessionMemory()
    summary_text = "Summary: completed the refactor"
    continuation = SessionMemory._format_continuation(summary_text, has_preserved=False)
    s.messages.append(Message(role="system", content=continuation))
    result = s._extract_prior_summary()
    assert result is not None
    assert "completed the refactor" in result
    assert "Continue executing" not in result


# ---------------------------------------------------------------------------
# Test 5 — compact() reduces estimate_tokens()
# ---------------------------------------------------------------------------

def test_compact_reduces_token_estimate():
    s = SessionMemory()
    # Add enough messages so compact() has something to remove
    for i in range(20):
        s.add("user", f"user message number {i} " + "x" * 200)
        s.add("assistant", f"assistant reply {i} " + "y" * 200)
    before = s.estimate_tokens()
    s.compact(preserve=4)
    after = s.estimate_tokens()
    assert after < before, f"Expected tokens to decrease: before={before} after={after}"


# ---------------------------------------------------------------------------
# Test 6 — two compact() calls keep tokens bounded
# ---------------------------------------------------------------------------

def test_double_compact_stays_bounded():
    s = SessionMemory()
    for i in range(30):
        s.add("user", f"message {i} " + "z" * 300)
        s.add("assistant", f"reply {i} " + "w" * 300)
    s.compact(preserve=4)
    after_first = s.estimate_tokens()

    # Add more messages and compact again
    for i in range(20):
        s.add("user", f"second round {i} " + "a" * 300)
        s.add("assistant", f"second reply {i} " + "b" * 300)
    s.compact(preserve=4)
    after_second = s.estimate_tokens()

    # The second compact must not blow past MAX_SUMMARY_CHARS // 4 for the
    # merged summary portion — just verify it doesn't grow unboundedly vs first.
    # A reasonable bound: second result is < 3× the post-first-compact size.
    assert after_second < after_first * 3, (
        f"Token growth looks unbounded: after_first={after_first} after_second={after_second}"
    )


# ---------------------------------------------------------------------------
# Test 7 — git_diff output is capped at MAX_DIFF_CHARS
# ---------------------------------------------------------------------------

def test_git_diff_capped_at_max_diff_chars(tmp_path):
    large_diff = "+" + "a" * 100_000  # far exceeds 8 000

    def fake_git(_cwd, args):
        if "--stat" in args:
            return "1 file changed, 1 insertion(+)"
        return large_diff

    with patch("src.memory_heist._git", side_effect=fake_git):
        result = git_diff(tmp_path, max_chars=MAX_DIFF_CHARS)

    assert result is not None
    # Each section body is capped at max_chars // 2 = 4 000; there's also a
    # header line, but the raw diff body portion must be truncated.
    assert len(result) < len(large_diff), "Diff was not truncated"
    # Total output must be well below 2 * MAX_DIFF_CHARS (two sections + headers)
    assert len(result) < 2 * MAX_DIFF_CHARS + 500


# ---------------------------------------------------------------------------
# Test 8 — ProjectContext.render() respects max_total_instruction_chars
# ---------------------------------------------------------------------------

def test_render_respects_instruction_budget(tmp_path):
    # Create a SWARM.md with lots of content
    swarm = tmp_path / "SWARM.md"
    swarm.write_text("# Instructions\n" + "word " * 5_000, encoding="utf-8")

    with patch("src.memory_heist.git_status", return_value=None), \
         patch("src.memory_heist.git_diff", return_value=None), \
         patch("src.memory_heist.git_log_oneline", return_value=None):
        project = ProjectContext.discover(tmp_path)

    small_render = project.render(max_total_instruction_chars=500)
    large_render = project.render(max_total_instruction_chars=10_000)

    assert len(small_render) < len(large_render), (
        "Smaller budget must produce a shorter render"
    )
