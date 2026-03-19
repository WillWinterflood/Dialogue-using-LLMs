'''
src/turn_logger.py

This logs the choices for each turn, good for memory retrieval and continuing the story.
'''

import json
import time
from src.config import FAILURE_LOG_PATH, LOG_PATH

def _retry_count(errors):
    count = 0
    for item in errors or []:
        text = str(item)
        if text.startswith("json_retry_attempt_"):
            try:
                count = max(count, int(text.rsplit("_", 1)[-1]) - 1)
            except Exception:
                continue
    return count

def _log_turn(llm, turn, player_choice, prompt_text, retrieval_meta, raw_output, parsed_output, valid, errors, timing_meta=None):
    retry_count = _retry_count(errors)
    row = {
        "timestamp": time.time(),
        "mode": "llm",
        "model": llm.model_id,
        "turn": turn,
        "player_choice_id": player_choice.get("id"),
        "player_choice_text": player_choice.get("text"),
        "player_action_type": player_choice.get("action_type"),
        "prompt": prompt_text,
        "prompt_tokens": retrieval_meta.get("prompt_tokens", 0),
        "memory_tokens": retrieval_meta.get("memory_tokens", 0),
        "retrieval_query": retrieval_meta.get("query", {}),
        "retrieval_candidate_count": retrieval_meta.get("candidate_count", 0),
        "retrieved_memory_ids": [item.get("event_id") for item in retrieval_meta.get("selected", [])],
        "retrieval_scores": [
            {
                "event_id": item.get("event_id"),
                "score": round(float(item.get("score", 0.0)), 4),
                "token_count": item.get("token_count"),
            }
            for item in retrieval_meta.get("selected", [])
        ],
        "raw_output": raw_output,
        "parsed_output": parsed_output,
        "valid": valid,
        "errors": errors,
        "had_repair": retry_count > 0,
        "retry_count": retry_count,
    }
    if isinstance(timing_meta, dict):
        row["timing"] = timing_meta
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")

def _log_failure(
    llm,
    turn,
    player_choice,
    prompt_text,
    retrieval_meta,
    *,
    current_npc,
    current_location,
    arc_state,
    raw_output,
    errors,
    attempts,
    timing_meta=None,
):
    row = {
        "timestamp": time.time(),
        "mode": "llm_failure",
        "failure_type": "validation_exhausted",
        "model": llm.model_id,
        "turn": turn,
        "attempts_exhausted": attempts,
        "player_choice_id": player_choice.get("id"),
        "player_choice_text": player_choice.get("text"),
        "player_action_type": player_choice.get("action_type"),
        "current_npc": current_npc,
        "current_location": current_location,
        "arc_phase": arc_state.get("phase"),
        "arc_next_required_beat": arc_state.get("next_required_beat"),
        "arc_next_required_goal": arc_state.get("next_required_goal"),
        "prompt": prompt_text,
        "prompt_tokens": retrieval_meta.get("prompt_tokens", 0),
        "memory_tokens": retrieval_meta.get("memory_tokens", 0),
        "retrieval_query": retrieval_meta.get("query", {}),
        "retrieval_candidate_count": retrieval_meta.get("candidate_count", 0),
        "retrieved_memory_ids": [item.get("event_id") for item in retrieval_meta.get("selected", [])],
        "raw_output": raw_output,
        "errors": errors,
    }
    if isinstance(timing_meta, dict):
        row["timing"] = timing_meta
    with FAILURE_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")
