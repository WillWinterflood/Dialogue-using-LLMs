# Dialogue-in-LLMs

## Overview
This project explores constrained dialogue generation with local LLMs for dissertation research on coherence and conditioning.

Current direction is incremental:
- Commit 1: baseline
- Commit 2: prove local model loading and generation.
- Commit 3a: introduce a strict JSON prompt contract + keeping the ReadME up to date

## Current Runtime (Commit 3a)
`game.py` runs a minimal local chat loop:
- `input() -> build prompt -> call local LLM -> log -> print`

The prompt template is stored in:
- `prompts/prompt_v1.txt`

Expected model format (prompt-level only for now):
- `npc_dialogue` (string)
- `state_updates` (object)
- `memory_summary` (string)

SB:
- At this stage, JSON is prompted but not fully enforced by code-level validation yet.

## Setup
```bash
pip install -r requirements.txt
```

## Run
```bash
python game.py
```

Environment variables right now:
- `LOCAL_MODEL` (default: `Qwen/Qwen2.5-0.5B-Instruct`)
- `LOCAL_MAX_NEW_TOKENS` (default set in `game.py`)

## Logging
Turn logs are written to:
- `dialogue_log.jsonl`

Each row stores:
- timestamp
- model name
- user input
- assistant output
