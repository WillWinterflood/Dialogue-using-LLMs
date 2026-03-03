# Dialogue-in-LLMs

## Overview
This project explores how to keep LLM-driven game dialogue coherent and controllable.
The dissertation focus is on conditioning and constrained generation, moving from a simple local LLM loop to a structured dialogue pipeline.

## Current State (Commit 5b - Persistent state foundation)
The current runtime is intentionally simple:

1. A hardcoded prologue introduces the scenario and characters.
2. The player selects scripted prologue choices.
3. Control is handed to a local LLM.
4. The LLM must return strict JSON.
5. JSON is parsed and validated.
6. Dialogue and numbered choices are shown.
7. The player must select a choice number.
8. World state is saved each turn.
9. Turn memories are appended to JSONL files for later retrieval work.

Current files:
- `game.py`: thin entrypoint
- `src/prologue.py`: hardcoded prologue scene + scripted choices
- `src/llm_runtime.py`: local Hugging Face model load/generate wrapper
- `src/choice_loop.py`: prompt build, JSON extraction/validation, logging, choice loop
- `src/state_store.py`: saves/loads world state
- `src/memory_store.py`: appends global + per-NPC memory journals
- `prompts/prompt_v1.txt`: base prompt contract

## JSON Contract (Current)
The dynamic loop currently expects:
- `narrator` (string)
- `speaker` (string)
- `reply` (string)
- `choices` (list, 2-4 items)
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

Optional environment variables:
- `LOCAL_MAX_NEW_TOKENS` (default defined in `src/llm_runtime.py`)

## Logging
Each turn is appended to:
- `dialogue_log.jsonl`
- `data/memory/turns.jsonl`
- `data/memory/<npc_name>.jsonl`

snapshot is saved to:
- `data/state/world_state.json`

Logged fields include:
- timestamp
- model
- turn
- user input
- prompt
- raw model output
- parsed output
- valid flag
- validation errors

