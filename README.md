# Dialogue-in-LLMs

## Overview
This project explores constrained dialogue generation with local LLMs for dissertation research on coherence and conditioning.

Current direction is incremental:
- Commit 1: baseline
- Commit 2: prove local model loading and generation.
- Commit 3a: introduce a strict JSON prompt contract.
- Commit 3b: add JSON parsing and minimal schema validation in runtime.

## Current Runtime (Commit 3b)
`game.py` runs a small local chat loop:
- `input() -> build prompt -> call local LLM -> parse/validate JSON -> log -> print`

The prompt template is stored in:
- `prompts/prompt_v1.txt`

Expected model format:
- `npc_dialogue` (string)
- `state_updates` (object)
- `memory_summary` (string)

Validation now enforces:
- required keys are present
- key types are correct
- unexpected keys are flagged

If output is invalid:
- the loop continues without crashing
- validation errors are shown and logged

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
- prompt
- raw output
- parsed output
- valid boolean
- validation errors
