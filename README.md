# Dialogue-in-LLMs

## Overview
This project explores how to keep LLM-driven game dialogue coherent and controllable.
The dissertation focus is on conditioning and constrained generation, moving from a simple local LLM loop to a structured dialogue pipeline.

## Current State (Commit 4 - Choice Driven)
The current runtime is intentionally simple:

1. A hardcoded prologue introduces the scenario and characters.
2. The player selects scripted prologue choices.
3. Control is handed to a local LLM.
4. The LLM must return strict JSON.
5. JSON is parsed and validated.
6. Dialogue and numbered choices are shown.
7. The player must select a choice number.

Current files:
- `game.py`: thin entrypoint
- `src/prologue.py`: hardcoded prologue scene + scripted choices
- `src/llm_runtime.py`: local Hugging Face model load/generate wrapper
- `src/choice_loop.py`: prompt build, JSON extraction/validation, logging, choice loop
- `prompts/prompt_v1.txt`: base prompt contract

## JSON Contract (Current)
The dynamic loop currently expects:
- `narrator` (string)
- `speaker` (string)
- `reply` (string)
- `choices` (list, 2-4 items)
- `state_updates` (object)
- `memory_summary` (string)

If the model fails to produce valid JSON after retry, the session ends (no fallback mode).

## Setup
```bash
pip install -r requirements.txt
```

## Run
```bash
python game.py
```

Optional environment variables:
- `LOCAL_MODEL` (default: `Qwen/Qwen2.5-0.5B-Instruct`)
- `LOCAL_MAX_NEW_TOKENS` (default defined in `src/llm_runtime.py`)

## Logging
Each turn is appended to:
- `dialogue_log.jsonl`

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

## Research Roadmap (What Comes Next)
The next commits will move toward a full constrained dialogue pipeline:

1. **Short-term memory carry-over**
- Keep recent validated turn summaries in context.
- Improve local coherence without full retrieval yet.

2. **State model + write-back**
- Introduce explicit world state files (quests, inventory, NPC flags, location).
- Apply only validated `state_updates` to state.

3. **Lightweight retrieval (pre-RAG stage)**
- Retrieve top-k relevant past events from logs using tags + recency.
- Inject only relevant memories instead of full history.

4. **RAG-style memory retrieval**
- Move from naive history to retrieval-driven memory selection.
- Evaluate whether retrieval improves consistency and perceived coherence.

5. **Narrative arc constraints**
- Add arc/checkpoint state (phase, required beats, deadlines).
- Enforce beat progression and pacing at validation time.

6. **Constraint layer expansion**
- Schema validation -> world consistency checks -> arc compliance checks.
- Regenerate when constraints fail.

7. **Evaluation framework**
- Compare constrained vs less-constrained conditions.
- Use logs and user study metrics (coherence, consistency, responsiveness, detectability of handoff from hardcoded to LLM).

## Why This Incremental Approach
The project intentionally builds constraints in layers so each commit demonstrates one measurable step:
- model runs locally
- structured outputs
- validation
- choice-driven control
- memory/retrieval
- world + arc enforcement

This supports a clear methodology narrative and makes results easier to analyze in the dissertation.
