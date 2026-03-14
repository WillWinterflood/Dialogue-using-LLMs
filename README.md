# Dialogue-in-LLMs

## Overview
This project explores how to keep LLM-driven game dialogue coherent and controllable.
The dissertation focus is on conditioning + constrained generation, moving from a simple local loop to a structured dialogue pipeline with persistent state and memory retrieval.

## Current State
The current runtime flow:

1. A hardcoded prologue introduces the scenario and characters.
2. The player selects scripted prologue choices.
3. Dynamic mode starts with a local LLM.
4. The loop retrieves recent global turns + NPC turns, then injects top summaries into the prompt.
5. The LLM must return strict JSON.
6. Deterministic story rules handle canonical quest/scene progression before the prompt is built.
7. JSON is parsed/validated with retry-on-invalid.
8. Dialogue and 2-3 numbered choices are shown, with at least one directed progress option when needed.
9. The player selects a choice number.
10. Canonical world state + memory logs are persisted each turn.

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
- `choices` (list, 2-3 items)
- `state_updates` (object)
- `memory_summary` (string)

Validation now enforces:
- required keys are present
- key types are correct
- `speaker` matches current NPC
- `reply` is non-empty and not a verbatim copy of player input
- `choices` contain 2-3 non-empty items after cleaning
- `state_updates` are treated as low-authority ambient hints only

If output is invalid:
- the loop retries with a repair instruction
- if still invalid after max retries, a safe fallback turn is used

## Requirements
- Python 3.10+
- NVIDIA GPU with CUDA available (runtime is CUDA-only) -> can be changed for other GPUs

## Setup (PowerShell)
```bash
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run
```bash
py -3 game.py
```

Optional environment variables:
- `LOCAL_MODEL_ID` (default: `Qwen/Qwen2.5-1.5B-Instruct`)
- `LOCAL_MAX_NEW_TOKENS` (default: `96`)

## Retrieval Knobs
Current retrieval parameters in `src/choice_loop.py`:
- `MEMORY_RECENT_TURNS = 8`
- `MEMORY_NPC_TURNS = 20`
- `MEMORY_TOP_K = 4`

## Logging
Each turn is appended to:
- `dialogue_log.jsonl`
- `data/memory/turns.jsonl`
- `data/memory/<npc_name>.jsonl`

State snapshot is saved to:
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
