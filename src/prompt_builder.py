import json
from src.config import ALLOWED_STATE_UPDATE_KEYS, PROMPT_PATH, PROMPT_RECENT_MESSAGES, VALID_TIME_OF_DAY

def _load_prompt_template():
    if not PROMPT_PATH.exists():
        raise RuntimeError(f"Prompt file not found: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8").strip()

def _build_prompt(
    *,
    prompt_template,
    prologue_summary,
    state,
    player_choice,
    memory_summaries,
    arc_state,
    recent_messages,
    turn,
    known_locations,
    known_quests,
    story_transition,
    required_choice_count=2,
    forced_choices=None,
):
    recent = [message for message in recent_messages if message.get("role") != "system"]
    recent = recent[-PROMPT_RECENT_MESSAGES:]
    if recent:
        recent_text = "\n".join(f"{message['role']}: {message['content']}" for message in recent)
    else:
        recent_text = "none"

    memory_block = "\n".join(f"- {summary}" for summary in memory_summaries) if memory_summaries else "none"

    state_slice = {
        "current_location": state.get("current_location", ""),
        "current_npc": state.get("current_npc", ""),
        "time_of_day": state.get("time_of_day", "night"),
        "day": state.get("day", 1),
        "active_quests": state.get("active_quests", {}),
        "quest_flags": state.get("quest_flags", {}),
        "inventory": state.get("inventory", []),
        "last_narrator": state.get("last_narrator", ""),
    }

    return (
        f"{prompt_template}\n\n"
        "PROLOGUE:\n"
        f"{prologue_summary}\n\n"
        "CURRENT STORY BEAT:\n"
        f"{story_transition or 'none'}\n\n"
        "STATE:\n"
        f"{json.dumps(state_slice, separators=(',', ':'))}\n\n"
        "PLAYER ACTION:\n"
        f"- choice_id: {player_choice.get('id')}\n"
        f"- action_type: {player_choice.get('action_type')}\n"
        f"- spoken_text: {player_choice.get('text')}\n\n"
        "ARC GOAL:\n"
        f"- phase: {arc_state.get('phase')}\n"
        f"- next_required_beat: {arc_state.get('next_required_beat') or 'none'}\n"
        f"- next_required_goal: {arc_state.get('next_required_goal')}\n"
        f"- beat_deadline_turn: {arc_state.get('beat_deadline_turn')}\n"
        f"- steering_strength: {arc_state.get('steering_strength', 'soft')}\n\n"
        "RELEVANT MEMORIES:\n"
        f"{memory_block}\n\n"
        "RECENT CONTEXT:\n"
        f"{recent_text}\n\n"
        "WORLD RULES:\n"
        f"- turn: {turn}\n"
        f"- known locations are: {', '.join(known_locations) if known_locations else 'none'}\n"
        f"- active quest ids in memory are: {', '.join(known_quests) if known_quests else 'none'}\n"
        f"- only use these state_updates keys: {', '.join(sorted(ALLOWED_STATE_UPDATE_KEYS))}\n"
        "- use state_updates only for small ambient changes such as time passing.\n"
        "- do not change quest status, inventory, current_npc, or current_location in state_updates.\n"
        f"- time_of_day must be one of: {', '.join(sorted(VALID_TIME_OF_DAY))}\n\n"
        "CHOICE QUALITY GUARDRAILS:\n"
        f"- choices must be exactly {required_choice_count} unique object{'s' if required_choice_count != 1 else ''} with id, text, action_type.\n"
        + (
            f"- this is a locked story beat; the only valid next choice is: {forced_choices[0]['text']}\n"
            if forced_choices and len(forced_choices) == 1
            else "- if choices are repeating from the previous turn, replace one with a concrete next-step question.\n"
              "- include at least one concrete lead, travel, or evidence-focused next step when possible."
        )
    )
