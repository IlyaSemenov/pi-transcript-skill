---
name: pi-transcript
description: Parse pi.dev session files from ~/.pi/agent/sessions, extracting user prompts and assistant text responses while stripping tool calls, thinking blocks, and other noise. Use when the user asks to analyze, review, summarize, or continue a pi session.
compatibility: Requires python3. Sessions are read from ~/.pi/agent/sessions by default.
---

# Pi Transcript

## Overview

Extract clean conversational text from pi.dev session JSONL files. The helper script parses session files, keeps only user messages and assistant text responses, and strips tool calls, tool results, thinking blocks, and other non-conversational noise.

This is used to prepare a clean session transcript for downstream analysis — code review, summarization, context continuation, or any other task.

## When to Use

Use this skill when the user asks to:

- "Review the previous session" / "сделай code review предыдущей сессии"
- "Summarize the last session" / "сделай свёртку последней сессии"
- "Analyze session {session-id}" / "проанализируй сессию {session-id}"
- "Continue from where we left off" / "продолжи с того места"
- "Show me what happened in the last session"
- Any request that involves reading or analyzing a pi.dev session's conversational content

When running **inside pi.dev**, the skill can infer the current project's sessions automatically.
When running in another agent, the user should specify "pi session" or "pi.dev session" to disambiguate.

## Workflow

1. **Identify the target session.**
   - If the user says "previous session" or "last session" and you are inside pi.dev, use `--latest` to get the most recent session in `~/.pi/agent/sessions`.
   - If the user provides a session ID (or prefix), use `--session-id <id>`.
   - If the user provides a file path, pass it directly.

2. **Extract the conversation.**

```bash
# Latest session (JSON, for agent consumption)
python3 scripts/extract_session.py --latest

# Specific session by ID or prefix
python3 scripts/extract_session.py --session-id 019dadb6

# Specific session file
python3 scripts/extract_session.py ~/.pi/agent/sessions/--home-user-projects-myapp--/2026-04-21T01-34-21-261Z_019dadac-924d-755c-ab3e-030fb7dc4f1d.jsonl

# List available sessions
python3 scripts/extract_session.py --list

# Human-readable text output (for terminal inspection)
python3 scripts/extract_session.py --latest --text
```

3. **Use the extracted text.**
   - For code review: pipe the JSON transcript into a review tool (e.g. `$claude-review`).
   - For summarization: analyze the session and produce a compact summary.
   - For context continuation: extract the key decisions and state to continue work.
   - For any other downstream analysis the user requests.
   - JSON output contains clean structured turns — no tool calls, no tool results, no thinking blocks.

## Output Format

### JSON mode (default)

The primary consumer is another agent or model. JSON is unambiguous and trivially parseable:

```json
{
  "session_file": "/path/to/session.jsonl",
  "turns": [
    {"role": "user", "text": "..."},
    {"role": "assistant", "text": "..."}
  ]
}
```

### Text mode (`--text`)

For quick human inspection in a terminal. Uses `=== USER ===` / `=== ASSISTANT ===` markers:

```
=== USER ===
Add retry logic to the publish function.

=== ASSISTANT ===
I'll add retry logic with exponential backoff...
```

Multiple consecutive assistant text blocks are preserved as separate turns (they represent distinct responses between tool calls).

### List mode (`--list`)

JSON array of session metadata by default. Use `--list --text` for a compact one-line-per-session format.

## Session Discovery

Sessions are stored as `.jsonl` files under `~/.pi/agent/sessions/<project-dir>/`.
Each project directory is named by encoding the working directory path (replacing `/` with `-` and wrapping in `--`).

The `--list` flag shows all available sessions sorted by timestamp (newest first).

## Resources

### scripts/

- `scripts/extract_session.py`: Parse pi.dev JSONL sessions and extract clean user/assistant text. Supports `--latest`, `--session-id`, `--list`, and `--text` flags. JSON output is the default.
