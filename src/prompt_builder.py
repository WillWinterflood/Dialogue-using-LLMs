'''
src/prompt_builder.py

Builds the prompt that gets sent to the LLM
'''

import json
from src.config import ALLOWED_STATE_UPDATE_KEYS, PROMPT_PATH, PROMPT_RECENT_MESSAGES, VALID_TIME_OF_DAY

# Per-NPC character notes injected into every prompt.
# Without these, a small model defaults to making every NPC helpful and open.
# Eli must be evasive and defensive — not a cooperative witness — otherwise the
# investigation has no tension and he volunteers information that should be extracted.
NPC_NOTES = {
    "eli": (
        "Eli is evasive and defensive. He gives short deflecting answers and denies direct "
        "involvement. He does not volunteer incriminating information freely. He never claims "
        "Mara sent or tasked him with anything — that would be a confession. He keeps answers "
        "vague, avoids specifics about the route entry, and deflects questions about the ledger."
    ),
    "mara": (
        "Mara is measured and authoritative. She speaks in short factual statements, "
        "waits for Alex to draw conclusions, and does not speculate beyond the evidence in front of her."
    ),
}

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
    current_npc = str(state.get("current_npc", "")).strip()
    last_speaker = str(state.get("last_speaker", "")).strip()
    spoken_npcs = state.get("spoken_npcs", [])
    if not isinstance(spoken_npcs, list):
        spoken_npcs = []
    npc_has_history = current_npc.lower() in {str(name).strip().lower() for name in spoken_npcs if str(name).strip()}

    current_npc_key = current_npc.lower()
    # Filter to messages that involve the current NPC specifically.
    # The old condition (last_speaker == current_npc) silently set recent_text
    # to "none" whenever there was any speaker mismatch — e.g. after a prologue
    # handoff — which stripped the model of all conversation history mid-session.
    npc_recent = [
        m for m in recent_messages
        if str(m.get("npc", "")).strip().lower() == current_npc_key
    ]
    npc_recent = npc_recent[-PROMPT_RECENT_MESSAGES:]
    recent_text = (
        "\n".join(f"{m['role']}: {m['content']}" for m in npc_recent)
        if npc_recent else "none"
    )

    memory_block = "\n".join(f"- {summary}" for summary in memory_summaries) if memory_summaries else "none"

    if last_speaker.lower() == current_npc.lower():
        last_memory_summary = state.get("last_memory_summary", "")
        last_narrator = state.get("last_narrator", "")
    else:
        last_memory_summary = ""
        last_narrator = ""

    #Problem was that sometimes the NPCs prompts were becoming a bit hallucinated, so we need to make sure that if theter is a new NPC introduced then its the frst conversation with them
    if current_npc and not npc_has_history: 
        npc_knowledge_rule = (
            f"- this is the first active conversation with {current_npc}; they only know what Alex just said, "
            "what they personally observed, and facts surfaced in retrieved memories tied to them.\n"
            f"- {current_npc} must not speak as if they heard the previous NPC's private conclusions.\n"
        )
    else:
        #So this means that only the active NPC knows the prior conversation
        npc_knowledge_rule = (
            f"- {current_npc or 'The active NPC'} only knows their own prior conversations, the current scene, "
            "and facts Alex has said aloud in this scene.\n"
        )

    if forced_choices and len(forced_choices) == 1:
        choice_guardrail_block = (
            f"- this is a locked story beat; the only valid next choice is: {forced_choices[0]['text']}\n"
        )
    else:
        #Forcing the LLM to move on and follow at least one concrete lead
        choice_guardrail_block = (
            "- if choices are repeating from the previous turn, replace one with a concrete next-step question.\n"
            "- include at least one concrete lead, travel, or evidence-focused next step when possible.\n"
            "- at least one choice must move to a new location or introduce new information not mentioned this turn.\n"
            "- never offer the same choice text that appeared in the previous turn.\n"
            "- do not paraphrase the previous NPC reply back to the player.\n"
            "- do not offer case closure unless the investigation has already been explicitly resolved."
        )

    state_slice = {
        "current_location": state.get("current_location", ""),
        "current_npc": current_npc,
        "time_of_day": state.get("time_of_day", "night"),
        "day": state.get("day", 1),
        "active_quests": state.get("active_quests", {}),
        "quest_flags": state.get("quest_flags", {}),
        "inventory": state.get("inventory", []),
        "last_memory_summary": last_memory_summary,
        "last_narrator": last_narrator,
    }

    return (
        f"{prompt_template}\n\n"
        "PROLOGUE:\n"
        f"{prologue_summary}\n\n"
        "CURRENT STORY HANDOFF:\n"
        f"{story_transition or 'none'}\n\n"
        "STATE:\n"
        f"{json.dumps(state_slice, separators=(',', ':'))}\n\n"
        "PLAYER ACTION:\n"
        f"- choice_id: {player_choice.get('id')}\n"
        f"- action_type: {player_choice.get('action_type')}\n"
        f"- spoken_text: {player_choice.get('text')}\n\n"
        "CHECKPOINT STATUS:\n"
        f"- phase: {arc_state.get('phase')}\n"
        f"- current_checkpoint_id: {arc_state.get('next_required_beat') or 'none'}\n"
        f"- current_checkpoint_goal: {arc_state.get('next_required_goal')}\n"
        f"- next_checkpoint_id: {arc_state.get('next_checkpoint_id') or 'none'}\n"
        f"- next_checkpoint_goal: {arc_state.get('next_checkpoint_goal') or 'none'}\n"
        f"- completed_checkpoints: {', '.join(arc_state.get('completed_beats', [])) or 'none'}\n"
        f"- beat_deadline_turn: {arc_state.get('beat_deadline_turn')}\n"
        f"- steering_strength: {arc_state.get('steering_strength', 'soft')}\n\n"
        "RELEVANT MEMORIES:\n"
        f"{memory_block}\n\n"
        "WORLD RULES:\n"
        f"- turn: {turn}\n"
        f"- known locations are: {', '.join(known_locations) if known_locations else 'none'}\n"
        f"- active quest ids in memory are: {', '.join(known_quests) if known_quests else 'none'}\n"
        f"- only use these state_updates keys: {', '.join(sorted(ALLOWED_STATE_UPDATE_KEYS))}\n"
        "- use state_updates only for small ambient changes such as time passing.\n"
        "- do not change quest status, inventory, current_npc, or current_location in state_updates.\n"
        "- keep the reply in the current NPC's own voice; do not answer as another NPC.\n"
        "- PROLOGUE and STATE are author context for consistency, not proof that the active NPC personally knows every fact in them.\n"
        "- continue directly from the current scene and the prologue handoff; do not restart the investigation.\n"
        f"- move naturally toward the current checkpoint: {arc_state.get('next_required_beat') or 'none'}.\n"
        "- do not skip ahead to a later checkpoint unless the current checkpoint has clearly been satisfied in-scene.\n"
        f"{npc_knowledge_rule}"
        f"- time_of_day must be one of: {', '.join(sorted(VALID_TIME_OF_DAY))}\n\n"
        "NPC CHARACTER:\n"
        f"{NPC_NOTES.get(current_npc_key, f'{current_npc} responds naturally to the scene.')}\n\n"
        # RECENT CONTEXT is placed last so it sits closest to the generation point.
        # A small model (1.5B) attends most strongly to recent tokens — burying this
        # in the middle of the prompt caused the NPC to ignore prior conversation.
        "RECENT CONTEXT:\n"
        f"{recent_text}\n\n"
        "CHOICE QUALITY GUARDRAILS:\n"
        f"- choices must be exactly {required_choice_count} unique object{'s' if required_choice_count != 1 else ''} with id, text, action_type.\n"
        f"{choice_guardrail_block}"
    )
