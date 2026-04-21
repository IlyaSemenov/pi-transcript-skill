# pi-transcript

Extract clean conversational text from pi.dev session files — user prompts and assistant prose responses only, with tool calls, thinking blocks, and other noise stripped away.

Designed to prepare clean session transcripts for downstream analysis by other agents or models — code review, summarization, context continuation, or any other task.

## Install

```bash
npx skills add -g https://github.com/IlyaSemenov/pi-transcript-skill
```

## Requirements

- `python3` must be available

## What It Does

The skill adds `$pi-transcript`, a session extraction workflow for agents.
You ask the agent to extract a pi.dev session's conversational content for any kind of downstream analysis — code review, session summarization, context continuation, or any other task that needs a clean session transcript.

It is meant for:

- **Analyze a previous session** — code review, summarization, or context extraction
- **Session inspection** — see what happened in a specific session
- **Session listing** — discover available sessions

## How It Works

The helper script at [skills/pi-transcript/scripts/extract_session.py](skills/pi-transcript/scripts/extract_session.py) parses pi.dev JSONL session files from `~/.pi/agent/sessions/`.

Each session file is a JSONL where each line is a JSON object with a `type` field (`session`, `message`, `model_change`, `thinking_level_change`). The script:

1. Filters for `message` entries with `role` `user` or `assistant`
2. Extracts only `type: "text"` content items from each message
3. Skips `toolCall`, `toolResult`, `thinking`, `image`, and other non-text content
4. Outputs in one of two formats:
   - **JSON (default)** — structured `{"turns": [...]}` for agent consumption. Unambiguous, trivially parseable.
   - **Text (`--text`)** — `=== USER ===` / `=== ASSISTANT ===` blocks for human inspection in a terminal.

## Usage

After installation, ask your agent to use `$pi-transcript`.

Examples:

```text
Use $pi-transcript to extract the latest session, then analyze it.
```

```text
Show me what happened in pi session 019dadb6.
```

```text
Make a code review of the previous pi session.
```

```text
Summarize the last pi session.
```

```text
Extract context from pi session 019dadb6 so I can continue.
```

### Direct Script Usage

```bash
# List all sessions
python3 scripts/extract_session.py --list

# Extract latest session (JSON, default)
python3 scripts/extract_session.py --latest

# Extract by session ID (or prefix)
python3 scripts/extract_session.py --session-id 019dadb6

# Human-readable text output
python3 scripts/extract_session.py --latest --text
```

## Notes

- Sessions are read from `~/.pi/agent/sessions/` by default. Override with `--sessions-dir`.
- Session IDs can be specified as full IDs or prefixes (e.g., just the timestamp part).
- The `--list` flag shows all sessions sorted newest-first with project directory info.

## Development

Tests live in [skills/pi-transcript/tests/](skills/pi-transcript/tests/) and use pytest.

Run with `uv` (no setup — pytest is fetched on demand):

```bash
cd skills/pi-transcript
uv run --with pytest python -m pytest tests/ -v
```

Or with pytest already available:

```bash
cd skills/pi-transcript
python3 -m pytest tests/ -v
```
