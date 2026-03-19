'''
/src/memory_retrieval.py

Scoring logic - How relevant a past memory is to the current situation
+ Retrieval logic 
'''
import re

from src.choice_formatter import _slugify
from src.config import MEMORY_NPC_TURNS, MEMORY_RECENT_TURNS, MEMORY_TOKEN_BUDGET, MEMORY_TOP_K, STOPWORDS

def _tokenize_for_match(text):
    tokens = set()
    for token in re.findall(r"[a-z0-9_]+", str(text or "").lower()):
        if len(token) < 3 or token in STOPWORDS:
            continue
        tokens.add(token)
    return tokens

def _build_auto_memory_summary(speaker_text, reply_text, current_npc="", current_location=""):
    speaker = speaker_text.strip() or str(current_npc or "NPC").strip() or "NPC"
    location = str(current_location or "current location").strip()
    reply_clean = " ".join(str(reply_text or "").strip().split())
    if reply_clean:
        if len(reply_clean) > 120:
            reply_clean = reply_clean[:117].rstrip() + "..."
        return f"{speaker} replied at {location}: {reply_clean}"
    return f"{speaker} spoke with Alex at {location}."

def _derive_tags(reply_text, memory_summary, current_npc, current_location, active_quests):
    tags = []
    seen = set()

    def add_tag(value):
        tag = _slugify(value)
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)

    add_tag(current_npc)
    add_tag(current_location)
    for quest_id in sorted(active_quests.keys()):
        add_tag(quest_id)
    for term in sorted(_tokenize_for_match(f"{reply_text} {memory_summary}")):
        add_tag(term)
        if len(tags) >= 6:
            break
    return tags[:6]

def _build_retrieval_query(player_choice, world_state, current_npc):
    active_quest_ids = sorted(world_state.get("active_quests", {}).keys())
    recent_dialogue = []
    last_player_action = world_state.get("last_player_action")
    last_reply = world_state.get("last_reply")
    if isinstance(last_player_action, str) and last_player_action.strip():
        recent_dialogue.append(last_player_action.strip())
    if isinstance(last_reply, str) and last_reply.strip():
        recent_dialogue.append(last_reply.strip())

    keywords = sorted(
        _tokenize_for_match(
            " ".join(
                [
                    str(player_choice.get("id", "")),
                    str(player_choice.get("text", "")),
                    str(current_npc or ""),
                    " ".join(active_quest_ids),
                    " ".join(recent_dialogue),
                ]
            )
        )
    )
    return {
        "choice_id": player_choice.get("id"),
        "choice_text": player_choice.get("text"),
        "action_type": player_choice.get("action_type"),
        "current_npc": current_npc,
        "active_quest_ids": active_quest_ids,
        "recent_dialogue": recent_dialogue[-4:],
        "keywords": keywords,
    }

def _score_memory_candidate(event, query, turn):
    event_id = str(event.get("event_id", "")).strip() or f"legacy_{event.get('turn', 0)}"
    quest_ids = {str(item).strip() for item in event.get("quest_ids", []) if str(item).strip()}

    tag_terms = set()
    for raw_tag in event.get("tags", []):
        tag_terms.update(_tokenize_for_match(raw_tag))

    text_terms = _tokenize_for_match(
        " ".join(
            [
                str(event.get("memory_summary", "")),
                str(event.get("reply", "")),
                str(event.get("choice_text", "")),
                str(event.get("choice_id", "")),
            ]
        )
    )

    query_terms = set(query.get("keywords", []))
    quest_overlap = quest_ids & set(query.get("active_quest_ids", []))
    keyword_overlap = query_terms & (tag_terms | text_terms)
    same_npc = str(event.get("current_npc", "")).strip().lower() == str(query.get("current_npc", "")).strip().lower()
    turns_ago = max(0, turn - int(event.get("turn", 0) or 0))
    recency_score = 1.0 / (1 + turns_ago)

    importance = event.get("importance", 3)
    if isinstance(importance, bool) or not isinstance(importance, int):
        importance = 3
    importance_score = max(0, min(10, importance)) / 10.0

    event_type = str(event.get("event_type", "dialogue")).strip().lower()
    if event_type == "fallback":
        importance_score *= 0.4

    constraint_bonus = 0.0
    if quest_overlap:
        constraint_bonus += 1.5
    if same_npc:
        constraint_bonus += 0.35
    if event_type in {"promise", "debt", "threat"} and same_npc:
        constraint_bonus += 0.75

    score = len(keyword_overlap) * 1.25 + recency_score + importance_score + constraint_bonus
    return {
        "event_id": event_id,
        "event": event,
        "score": score,
        "passes_filter": bool(keyword_overlap or quest_overlap or same_npc),
    }

def _retrieve_memories(
    player_choice,
    *,
    memory_store,
    current_npc,
    current_location,
    world_state,
    turn,
    count_tokens,
    is_fallback_event,
):
    query = _build_retrieval_query(player_choice, world_state, current_npc)
    npc_turns = memory_store.load_npc_turns(current_npc, MEMORY_NPC_TURNS)
    recent = memory_store.load_recent_turns(MEMORY_RECENT_TURNS)

    seen_ids = set()
    combined = []
    for event in npc_turns + recent:
        if is_fallback_event(event):
            continue
        event_id = str(event.get("event_id", "")).strip() or f"legacy_{event.get('turn', 0)}_{len(combined)}"
        if event_id in seen_ids:
            continue
        seen_ids.add(event_id)
        combined.append(event)

    scored = []
    for event in combined:
        item = _score_memory_candidate(event, query, turn)
        if item["passes_filter"]:
            scored.append(item)
    if not scored:
        for event in combined[-MEMORY_RECENT_TURNS:]:
            scored.append(_score_memory_candidate(event, query, turn))
    scored.sort(key=lambda item: item["score"], reverse=True)

    selected = []
    summaries = []
    memory_tokens = 0
    for item in scored:
        summary = str(item["event"].get("memory_summary", "")).strip()
        if not summary:
            summary = _build_auto_memory_summary(
                str(item["event"].get("speaker", "")),
                str(item["event"].get("reply", "")),
                current_npc=current_npc,
                current_location=current_location,
            )

        token_count = count_tokens(summary)
        if selected and memory_tokens + token_count > MEMORY_TOKEN_BUDGET:
            continue
        item["token_count"] = token_count
        selected.append(item)
        summaries.append(summary)
        memory_tokens += token_count
        if len(selected) >= MEMORY_TOP_K:
            break

    retrieval_meta = {
        "query": query,
        "selected": selected,
        "candidate_count": len(combined),
        "memory_tokens": memory_tokens,
        "prompt_tokens": 0,
    }
    return summaries, retrieval_meta

