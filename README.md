# Constrained Dialogue Generation for Video Games Using LLM (Qwen)

A dissertation research project exploring how constrained generation, retrieval-augmented memory, and deterministic story rules can be combined to produce coherent, controllable NPC dialogue using a locally-run large language model.

The scenario is a short investigation: the player (Alex) questions NPCs across two locations to uncover who tampered with a shipment, building evidence before making an accusation.

---

## How It Works

1. A scripted prologue introduces the scenario and seeds the memory store.
2. The player selects from numbered choices each turn.
3. Deterministic story rules enforce quest flag invariants and canonical scene transitions before any prompt is built.
4. Relevant memories are scored and retrieved using recency, NPC match, quest overlap, and cosine semantic similarity.
5. A structured prompt is built and sent to the local LLM.
6. The LLM must return strict JSON (narrator, speaker, reply, choices, state_updates, memory_summary).
7. Output is validated and repaired through a 4-stage retry pipeline.
8. World state and memory logs are persisted each turn.

---

## Requirements

- Python 3.10+
- NVIDIA GPU with CUDA (default) — edit `src/llm_runtime.py` to change device
  - I used this as this was my laptop GPU. 
- ~2 GB disk space for model weights (downloaded automatically on first run)

---

## Setup (PowerShell)

Can set up a virtual environment if you want, it will not make much difference if you dont though

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
---

## Run

```powershell
py -3 game.py
```

On first run the Hugging Face model weights will be downloaded automatically.  
On subsequent runs you will be asked whether to continue the previous session or restart.

---

## Environment Variables (Optional)

| Variable | Default | Description |
|---|---|---|
| `LOCAL_MODEL_ID` | `Qwen/Qwen2.5-1.5B-Instruct` | Hugging Face model ID to load |
| `LOCAL_MAX_NEW_TOKENS` | `96` | Max tokens generated per turn |

---

## Project Structure

```
game.py                   Entry point
src/
  choice_loop.py          Main dialogue loop conductor
  prompt_builder.py       Structured prompt assembly
  output_validator.py     JSON validation and retry repair pipeline
  story_rules.py          Deterministic FSM for quest/scene progression
  memory_retrieval.py     Memory scoring and retrieval
  state_manager.py        World state, LLM importance rating, reflection
  memory_store.py         Append-only JSONL memory journals
  state_store.py          World state persistence and arc checkpoint plan
  embedder.py             Lazy sentence-embedding singleton (all-MiniLM-L6-v2)
  choice_formatter.py     Choice normalisation, deduplication, loop detection
  llm_runtime.py          Hugging Face model load/generate wrapper
  prologue.py             Scripted prologue scene and scripted choices
  config.py               All tunable constants
prompts/
  prompt_v1.txt           Base prompt contract sent to the LLM
tests/
  test_story_rules.py     Unit tests for deterministic story rule logic
data/
  memory/                 Per-turn and per-NPC memory journals (JSONL)
  state/                  Persisted world state (JSON)
dialogue_log.jsonl        Full turn log (raw output, parsed output, timing)
failure_log.jsonl         Log of turns where validation was exhausted
```

---

## Retrieval Tuning

Key constants in `src/config.py`:

| Constant | Default | Effect |
|---|---|---|
| `MEMORY_TOP_K` | `3` | Number of memories injected per turn |
| `MEMORY_TOKEN_BUDGET` | `350` | Max tokens allocated to memory block |
| `MEMORY_RECENT_TURNS` | `8` | Turns considered for recency scoring |
| `PROMPT_RECENT_MESSAGES` | `6` | Recent messages included in prompt context |

---

## Tests

```powershell
py -3 -m pytest tests
```
