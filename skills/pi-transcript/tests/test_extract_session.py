"""Tests for extract_session.py — parsing, extraction, and session discovery."""

import json
import textwrap
from pathlib import Path

import pytest

from extract_session import (
    _session_ts_to_iso,
    discover_sessions,
    extract_conversation,
    find_latest_session,
    find_session_by_id,
    format_conversation,
    main,
    parse_session,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cwd_to_dir(cwd: str) -> str:
    """Convert cwd to pi session directory name format."""
    return "--" + cwd.strip("/").replace("/", "-") + "--"


def _make_session_jsonl(
    tmp_path: Path,
    session_id: str = "2026-04-21T01-45-33-558Z_019dadb6-d476-70ba-99c3-cbd67c961811",
    cwd: str = "/home/user/test-project",
    entries: list[dict] | None = None,
) -> Path:
    """Create a minimal .jsonl session file and return its path."""
    project_dir = tmp_path / _cwd_to_dir(cwd)
    project_dir.mkdir(parents=True, exist_ok=True)
    session_file = project_dir / f"{session_id}.jsonl"

    lines: list[str] = []

    # Always add session header
    lines.append(json.dumps({
        "type": "session",
        "version": 3,
        "id": session_id.split("_", 1)[1] if "_" in session_id else session_id,
        "timestamp": "2026-04-21T01:45:33.558Z",
        "cwd": cwd,
    }))

    if entries is not None:
        for entry in entries:
            lines.append(json.dumps(entry))

    session_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return session_file


def _user_msg(text: str, **overrides: object) -> dict:
    base = {
        "type": "message",
        "id": "msg-user-1",
        "parentId": None,
        "timestamp": "2026-04-21T01:45:33.558Z",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": text}],
            "timestamp": 1776736512030,
        },
    }
    base.update(overrides)
    return base


def _assistant_msg(content_items: list[dict], **overrides: object) -> dict:
    base = {
        "type": "message",
        "id": "msg-assistant-1",
        "parentId": None,
        "timestamp": "2026-04-21T01:45:34.558Z",
        "message": {
            "role": "assistant",
            "content": content_items,
            "api": "openai-completions",
            "provider": "test",
            "model": "test-model",
        },
    }
    base.update(overrides)
    return base


def _text_item(text: str) -> dict:
    return {"type": "text", "text": text}


def _tool_call_item(name: str = "read", args: dict | None = None) -> dict:
    return {
        "type": "toolCall",
        "id": "call_123",
        "name": name,
        "arguments": args or {"path": "/some/file"},
    }


def _thinking_item(thought: str) -> dict:
    return {"type": "thinking", "thinking": thought, "thinkingSignature": "reasoning_content"}


def _tool_result_item(text: str) -> dict:
    return {
        "type": "message",
        "id": "msg-tool-result",
        "parentId": "msg-assistant-1",
        "timestamp": "2026-04-21T01:45:34.558Z",
        "message": {
            "role": "toolResult",
            "toolCallId": "call_123",
            "toolName": "read",
            "content": [{"type": "text", "text": text}],
            "isError": False,
        },
    }


# ---------------------------------------------------------------------------
# Test parse_session
# ---------------------------------------------------------------------------

class TestParseSession:
    def test_valid_jsonl(self, tmp_path: Path):
        p = tmp_path / "test.jsonl"
        p.write_text(
            '{"type":"session","version":3}\n'
            '{"type":"message","message":{"role":"user"}}\n',
            encoding="utf-8",
        )
        entries = parse_session(p)
        assert len(entries) == 2
        assert entries[0]["type"] == "session"
        assert entries[1]["type"] == "message"

    def test_empty_file(self, tmp_path: Path):
        p = tmp_path / "empty.jsonl"
        p.write_text("", encoding="utf-8")
        entries = parse_session(p)
        assert entries == []

    def test_blank_lines_skipped(self, tmp_path: Path):
        p = tmp_path / "blanks.jsonl"
        p.write_text('{"type":"session"}\n\n\n{"type":"message"}\n', encoding="utf-8")
        entries = parse_session(p)
        assert len(entries) == 2

    def test_invalid_json_lines_skipped(self, tmp_path: Path):
        p = tmp_path / "bad.jsonl"
        p.write_text('{"type":"session"}\nnot-json\n{"type":"message"}\n', encoding="utf-8")
        entries = parse_session(p)
        assert len(entries) == 2


# ---------------------------------------------------------------------------
# Test extract_conversation
# ---------------------------------------------------------------------------

class TestExtractConversation:
    def test_user_text_only(self):
        entries = [_user_msg("Hello, world!")]
        turns = extract_conversation(entries)
        assert len(turns) == 1
        assert turns[0]["role"] == "user"
        assert turns[0]["text"] == "Hello, world!"

    def test_assistant_text_only(self):
        entries = [_assistant_msg([_text_item("I can help with that.")])]
        turns = extract_conversation(entries)
        assert len(turns) == 1
        assert turns[0]["role"] == "assistant"
        assert turns[0]["text"] == "I can help with that."

    def test_tool_calls_filtered_out(self):
        entries = [
            _assistant_msg([
                _thinking_item("Let me think..."),
                _tool_call_item("read", {"path": "/tmp/file"}),
                _text_item("I checked the file."),
            ]),
        ]
        turns = extract_conversation(entries)
        assert len(turns) == 1
        assert turns[0]["text"] == "I checked the file."

    def test_tool_results_filtered_out(self):
        entries = [
            _assistant_msg([_tool_call_item()]),
            _tool_result_item("file contents here"),
            _assistant_msg([_text_item("Done!")]),
        ]
        turns = extract_conversation(entries)
        assert len(turns) == 1
        assert turns[0]["role"] == "assistant"
        assert turns[0]["text"] == "Done!"

    def test_full_conversation_flow(self):
        entries = [
            _user_msg("Fix the bug"),
            _assistant_msg([
                _thinking_item("Let me analyze"),
                _tool_call_item("bash", {"command": "grep foo bar"}),
            ]),
            _tool_result_item("foo found at line 42"),
            _assistant_msg([
                _tool_call_item("edit", {"path": "bar", "edits": []}),
                _text_item("Here's what I found and fixed:"),
            ]),
            _assistant_msg([_text_item("The bug was in line 42. Fixed!")]),
        ]
        turns = extract_conversation(entries)
        assert len(turns) == 3
        assert turns[0]["role"] == "user"
        assert turns[0]["text"] == "Fix the bug"
        assert turns[1]["role"] == "assistant"
        assert turns[1]["text"] == "Here's what I found and fixed:"
        assert turns[2]["role"] == "assistant"
        assert turns[2]["text"] == "The bug was in line 42. Fixed!"

    def test_empty_text_skipped(self):
        entries = [
            _user_msg("   "),
            _assistant_msg([_text_item("  \n  ")]),
            _assistant_msg([_tool_call_item()]),
        ]
        turns = extract_conversation(entries)
        assert turns == []

    def test_session_and_metadata_entries_ignored(self):
        entries = [
            {"type": "session", "version": 3, "id": "abc"},
            {"type": "model_change", "id": "x", "provider": "zai", "modelId": "glm-5.1"},
            {"type": "thinking_level_change", "id": "y", "thinkingLevel": "medium"},
            _user_msg("Hello"),
        ]
        turns = extract_conversation(entries)
        assert len(turns) == 1
        assert turns[0]["text"] == "Hello"

    def test_multiple_text_items_joined(self):
        entries = [
            _assistant_msg([
                _text_item("First paragraph."),
                _text_item("Second paragraph."),
            ]),
        ]
        turns = extract_conversation(entries)
        assert len(turns) == 1
        assert "First paragraph." in turns[0]["text"]
        assert "Second paragraph." in turns[0]["text"]
        assert "\n\n" in turns[0]["text"]

    def test_mixed_content_types(self):
        entries = [
            _assistant_msg([
                _thinking_item("hmm"),
                _tool_call_item("bash", {"command": "ls"}),
                {"type": "image", "image_url": "http://example.com/img.png"},
                _text_item("Here is the result."),
            ]),
        ]
        turns = extract_conversation(entries)
        assert len(turns) == 1
        assert turns[0]["text"] == "Here is the result."


# ---------------------------------------------------------------------------
# Test format_conversation
# ---------------------------------------------------------------------------

class TestFormatConversation:
    def test_single_turn(self):
        turns = [{"role": "user", "text": "Hello"}]
        output = format_conversation(turns)
        assert output == "=== USER ===\nHello\n"

    def test_multiple_turns(self):
        turns = [
            {"role": "user", "text": "Hello"},
            {"role": "assistant", "text": "Hi there!"},
        ]
        output = format_conversation(turns)
        assert "=== USER ===" in output
        assert "=== ASSISTANT ===" in output
        assert "Hello" in output
        assert "Hi there!" in output

    def test_empty(self):
        output = format_conversation([])
        assert output == ""


# ---------------------------------------------------------------------------
# Test _session_ts_to_iso
# ---------------------------------------------------------------------------

class TestSessionTsToIso:
    def test_standard_format(self):
        result = _session_ts_to_iso("2026-04-21T01-45-33-558Z")
        assert result == "2026-04-21T01:45:33.558+00:00"

    def test_no_fraction(self):
        result = _session_ts_to_iso("2026-04-21T01-45-33Z")
        assert result == "2026-04-21T01:45:33+00:00"


# ---------------------------------------------------------------------------
# Test session discovery
# ---------------------------------------------------------------------------

class TestDiscoverSessions:
    def test_finds_jsonl_files(self, tmp_path: Path):
        _make_session_jsonl(tmp_path)
        sessions = discover_sessions(tmp_path)
        assert len(sessions) == 1
        assert sessions[0]["cwd"] == "/home/user/test-project"

    def test_empty_dir(self, tmp_path: Path):
        sessions = discover_sessions(tmp_path)
        assert sessions == []

    def test_sorted_newest_first(self, tmp_path: Path):
        _make_session_jsonl(
            tmp_path,
            session_id="2026-04-20T10-00-00-000Z_older-session",
        )
        _make_session_jsonl(
            tmp_path,
            session_id="2026-04-21T10-00-00-000Z_newer-session",
        )
        sessions = discover_sessions(tmp_path)
        assert len(sessions) == 2
        # Newest first
        assert "newer-session" in sessions[0]["id"]
        assert "older-session" in sessions[1]["id"]


class TestFindSessionById:
    def test_exact_match(self, tmp_path: Path):
        _make_session_jsonl(tmp_path, session_id="2026-04-21T01-45-33-558Z_abc-123")
        result = find_session_by_id("2026-04-21T01-45-33-558Z_abc-123", tmp_path)
        assert result is not None

    def test_prefix_match(self, tmp_path: Path):
        _make_session_jsonl(tmp_path, session_id="2026-04-21T01-45-33-558Z_abc-123")
        result = find_session_by_id("2026-04-21T01-45-33-558Z_abc", tmp_path)
        assert result is not None

    def test_uuid_exact_match(self, tmp_path: Path):
        """Match by UUID part (after the underscore) alone."""
        _make_session_jsonl(tmp_path, session_id="2026-04-21T01-45-33-558Z_abc-123")
        result = find_session_by_id("abc-123", tmp_path)
        assert result is not None

    def test_uuid_prefix_match(self, tmp_path: Path):
        """Match by UUID prefix — the typical usage pattern."""
        _make_session_jsonl(tmp_path, session_id="2026-04-21T01-45-33-558Z_019dae23-63b0-7529-99f7-59ab09a6b144")
        result = find_session_by_id("019dae23", tmp_path)
        assert result is not None

    def test_not_found(self, tmp_path: Path):
        _make_session_jsonl(tmp_path, session_id="2026-04-21T01-45-33-558Z_abc-123")
        result = find_session_by_id("nonexistent", tmp_path)
        assert result is None

    def test_empty_dir(self, tmp_path: Path):
        result = find_session_by_id("anything", tmp_path)
        assert result is None


class TestFindLatestSession:
    def test_returns_newest(self, tmp_path: Path):
        _make_session_jsonl(
            tmp_path,
            session_id="2026-04-20T10-00-00-000Z_older",
        )
        _make_session_jsonl(
            tmp_path,
            session_id="2026-04-21T10-00-00-000Z_newer",
        )
        result = find_latest_session(tmp_path)
        assert result is not None
        assert "newer" in result.name

    def test_empty_dir(self, tmp_path: Path):
        result = find_latest_session(tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# Integration: parse a real-ish session file
# ---------------------------------------------------------------------------

class TestCliDefaultsJson:
    def test_extract_defaults_to_json(self, tmp_path: Path):
        """CLI without --text should output JSON."""
        import subprocess

        _make_session_jsonl(tmp_path, entries=[
            _user_msg("Hello"),
            _assistant_msg([_text_item("Hi there!")]),
        ])

        result = subprocess.run(
            ["python3", str(Path(__file__).parent.parent / "scripts" / "extract_session.py"),
             "--latest", "--sessions-dir", str(tmp_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "turns" in data
        assert len(data["turns"]) == 2
        assert data["turns"][0]["role"] == "user"

    def test_extract_text_flag(self, tmp_path: Path):
        """CLI with --text should output formatted text."""
        import subprocess

        _make_session_jsonl(tmp_path, entries=[
            _user_msg("Hello"),
            _assistant_msg([_text_item("Hi there!")]),
        ])

        result = subprocess.run(
            ["python3", str(Path(__file__).parent.parent / "scripts" / "extract_session.py"),
             "--latest", "--text", "--sessions-dir", str(tmp_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "=== USER ===" in result.stdout
        assert "=== ASSISTANT ===" in result.stdout

    def test_list_defaults_to_json(self, tmp_path: Path):
        """CLI --list without --text should output JSON."""
        import subprocess

        _make_session_jsonl(tmp_path)

        result = subprocess.run(
            ["python3", str(Path(__file__).parent.parent / "scripts" / "extract_session.py"),
             "--list", "--sessions-dir", str(tmp_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 1


class TestIntegration:
    def test_full_session_extraction(self, tmp_path: Path):
        entries = [
            {"type": "session", "version": 3, "id": "test-123", "timestamp": "2026-04-21T01:00:00.000Z", "cwd": "/tmp"},
            {"type": "model_change", "id": "mc1", "provider": "zai", "modelId": "glm-5.1"},
            _user_msg("Write a hello world program"),
            _assistant_msg([
                _thinking_item("Simple task"),
                _tool_call_item("bash", {"command": "echo hello"}),
            ]),
            _tool_result_item("hello"),
            _assistant_msg([
                _tool_call_item("write", {"path": "/tmp/hello.py", "content": "print('hello')"}),
                _text_item("I've created the file."),
            ]),
            _assistant_msg([_text_item("The program prints 'hello' when run.")]),
            _user_msg("Thanks!"),
            _assistant_msg([_text_item("You're welcome!")]),
        ]
        path = _make_session_jsonl(tmp_path, entries=entries)

        parsed = parse_session(path)
        turns = extract_conversation(parsed)

        assert len(turns) == 5
        assert turns[0] == {"role": "user", "text": "Write a hello world program"}
        assert turns[1] == {"role": "assistant", "text": "I've created the file."}
        assert turns[2] == {"role": "assistant", "text": "The program prints 'hello' when run."}
        assert turns[3] == {"role": "user", "text": "Thanks!"}
        assert turns[4] == {"role": "assistant", "text": "You're welcome!"}

        formatted = format_conversation(turns)
        assert "=== USER ===" in formatted
        assert "=== ASSISTANT ===" in formatted
        assert formatted.count("=== USER ===") == 2
        assert formatted.count("=== ASSISTANT ===") == 3
