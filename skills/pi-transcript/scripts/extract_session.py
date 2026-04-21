#!/usr/bin/env python3
"""
Extract user and assistant text from pi.dev session JSONL files.

Strips tool calls, tool results, thinking blocks, and other non-conversational
noise — keeping only the text that the user typed and the text that the model
wrote as prose.

Usage:
    python3 extract_session.py <session.jsonl>
    python3 extract_session.py --list [<sessions-dir>]
    python3 extract_session.py --latest [<sessions-dir>]
    python3 extract_session.py --session-id <id> [<sessions-dir>]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

SESSIONS_DIR = Path.home() / ".pi" / "agent" / "sessions"


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_session(path: Path) -> list[dict[str, Any]]:
    """Return a list of parsed JSON objects from a .jsonl session file."""
    entries: list[dict[str, Any]] = []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return entries
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def extract_conversation(entries: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Extract user/assistant text turns, skipping tool calls and other noise."""
    turns: list[dict[str, str]] = []
    for entry in entries:
        if entry.get("type") != "message":
            continue
        message = entry.get("message", {})
        role = message.get("role")
        if role not in ("user", "assistant"):
            continue

        # Collect only text items, skip toolCall, thinking, image, etc.
        text_parts: list[str] = []
        for item in message.get("content", []):
            if item.get("type") == "text" and item.get("text", "").strip():
                text_parts.append(item["text"].strip())

        combined = "\n\n".join(text_parts).strip()
        if not combined:
            continue

        turns.append({"role": role, "text": combined})

    return turns


def format_conversation(turns: list[dict[str, str]]) -> str:
    """Format turns into a human-readable transcript."""
    lines: list[str] = []
    for turn in turns:
        role_label = "USER" if turn["role"] == "user" else "ASSISTANT"
        lines.append(f"=== {role_label} ===")
        lines.append(turn["text"])
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Session discovery
# ---------------------------------------------------------------------------

def discover_sessions(sessions_dir: Path) -> list[dict[str, Any]]:
    """Walk the sessions directory and collect session metadata."""
    sessions: list[dict[str, Any]] = []
    if not sessions_dir.is_dir():
        return sessions

    for project_dir in sorted(sessions_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        for session_file in sorted(project_dir.glob("*.jsonl")):
            session_id = session_file.stem
            # Parse timestamp from the filename prefix: 2026-04-21T01-45-33-558Z_...
            parts = session_id.split("_", 1)
            timestamp_str = parts[0]
            try:
                # Replace the dash between date/time components for ISO parsing
                # Format: 2026-04-21T01-45-33-558Z  -> 2026-04-21T01:45:33.558Z
                iso_str = _session_ts_to_iso(timestamp_str)
                timestamp = datetime.fromisoformat(iso_str)
            except (ValueError, IndexError):
                timestamp = None

            # Extract cwd from session header
            cwd = ""
            try:
                first_line = session_file.read_text(encoding="utf-8").split("\n", 1)[0]
                header = json.loads(first_line)
                cwd = header.get("cwd", "")
            except (json.JSONDecodeError, OSError):
                pass

            sessions.append({
                "id": session_id,
                "file": str(session_file),
                "project_dir": project_dir.name,
                "timestamp": timestamp,
                "cwd": cwd,
            })

    # Sort by timestamp descending (newest first)
    sessions.sort(key=lambda s: s["timestamp"] or datetime.min, reverse=True)
    return sessions


def _session_ts_to_iso(ts: str) -> str:
    """Convert pi session timestamp format to ISO 8601.

    '2026-04-21T01-45-33-558Z' -> '2026-04-21T01:45:33.558+00:00'
    """
    # Split at T
    date_part, time_part = ts.split("T", 1)
    # time_part is like '01-45-33-558Z'
    # Remove trailing Z
    time_part = time_part.removesuffix("Z")
    segments = time_part.split("-")
    if len(segments) == 4:
        h, m, s, frac = segments
        return f"{date_part}T{h}:{m}:{s}.{frac}+00:00"
    elif len(segments) == 3:
        h, m, s = segments
        return f"{date_part}T{h}:{m}:{s}+00:00"
    else:
        return ts


def _session_uuid(stem: str) -> str:
    """Extract the UUID part of a session file stem.

    '2026-04-21T03-44-08-112Z_019dae23-63b0-7529-99f7-59ab09a6b144'
        -> '019dae23-63b0-7529-99f7-59ab09a6b144'
    """
    parts = stem.split("_", 1)
    return parts[1] if len(parts) == 2 else stem


def find_session_by_id(session_id: str, sessions_dir: Path) -> Path | None:
    """Find a session file by its full ID or by a prefix match.

    Matches against both the full file stem (timestamp_uuid) and the UUID
    part alone, so users can pass either format:
        --session-id 019dae23-63b0-7529-99f7-59ab09a6b144
        --session-id 019dae23          # prefix of UUID
    """
    sessions = discover_sessions(sessions_dir)
    # Exact match (full stem or UUID)
    for s in sessions:
        if s["id"] == session_id or _session_uuid(s["id"]) == session_id:
            return Path(s["file"])
    # Prefix match (full stem or UUID)
    for s in sessions:
        if s["id"].startswith(session_id) or _session_uuid(s["id"]).startswith(session_id):
            return Path(s["file"])
    return None


def find_latest_session(sessions_dir: Path) -> Path | None:
    """Find the most recent session file."""
    sessions = discover_sessions(sessions_dir)
    if not sessions:
        return None
    return Path(sessions[0]["file"])



# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def emit_json(data: Any) -> None:
    json.dump(data, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract user/assistant text from pi.dev sessions."
    )
    parser.add_argument(
        "session_file",
        nargs="?",
        help="Path to a specific .jsonl session file",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--list", "-l",
        action="store_true",
        help="List available sessions",
    )
    group.add_argument(
        "--latest",
        action="store_true",
        help="Extract from the latest session",
    )
    group.add_argument(
        "--session-id",
        metavar="ID",
        help="Extract a specific session by ID (or prefix)",
    )
    parser.add_argument(
        "--sessions-dir",
        default=str(SESSIONS_DIR),
        help=f"Sessions directory (default: {SESSIONS_DIR})",
    )
    parser.add_argument(
        "--text",
        action="store_true",
        dest="text_output",
        help="Output as human-readable formatted text instead of JSON",
    )
    args = parser.parse_args()

    sessions_dir = Path(args.sessions_dir)

    # --list mode
    if args.list:
        sessions = discover_sessions(sessions_dir)
        if args.text_output:
            for s in sessions:
                ts = s["timestamp"].isoformat() if s["timestamp"] else "?"
                print(f"{ts}  {s['project_dir']}  {s['id']}")
        else:
            emit_json(sessions)
        return 0

    # Determine which session file to use
    session_path: Path | None = None

    if args.latest:
        session_path = find_latest_session(sessions_dir)
        if not session_path:
            print("No sessions found.", file=sys.stderr)
            return 1
    elif args.session_id:
        session_path = find_session_by_id(args.session_id, sessions_dir)
        if not session_path:
            print(f"Session not found: {args.session_id}", file=sys.stderr)
            return 1
    elif args.session_file:
        session_path = Path(args.session_file)
        if not session_path.exists():
            print(f"File not found: {session_path}", file=sys.stderr)
            return 1
    else:
        parser.print_help()
        return 1

    entries = parse_session(session_path)
    turns = extract_conversation(entries)

    if args.text_output:
        output = format_conversation(turns)
        if output:
            print(output)
        else:
            print("No conversational text found in this session.", file=sys.stderr)
    else:
        emit_json({"session_file": str(session_path), "turns": turns})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
