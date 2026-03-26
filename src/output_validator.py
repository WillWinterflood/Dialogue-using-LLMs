'''
src/output_validator.py
This file ensures that the LLM outputs in the right form
ensures that it outputs valid JSON
'''

import json
import re

from src.choice_formatter import (
    _build_progress_choice,
    _coerce_choice_list,
    _choice_key,
    _enforce_progress_choice,
    _inject_story_choice,
    _normalise_choice,
    _replace_repeated_choices,
    _slugify,
)
from src.config import (
    ALLOWED_EVENT_TYPES,
    MAX_JSON_RETRY_ATTEMPTS,
    MAX_LLM_CHOICES,
    MIN_LLM_CHOICES,
    VALID_TIME_OF_DAY,
)
from src.memory_retrieval import _build_auto_memory_summary, _derive_tags

UNSUPPORTED_SCENE_PATTERNS = (
    r"\bmy room\b",
    r"\bthe woods\b",
    r"\binto the woods\b",
    r"\bforest\b",
    r"\bpurse\b",
    r"\bclothes\b",
    r"\bblacksmith\b",
    r"\boutskirts\b",
)

class OutputValidationExhausted(RuntimeError):
    def __init__(self, message, *, last_raw="", errors=None, attempts=0):
        super().__init__(message)
        self.last_raw = last_raw
        self.errors = list(errors or [])
        self.attempts = attempts


def _extract_json_object(raw_text):
    text = str(raw_text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    for index in range(start, len(text)):
        ch = text[index]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                chunk = text[start : index + 1]
                try:
                    return json.loads(chunk)
                except Exception:
                    return None
    return None

def _sanitize_state_updates(updates):
    if not isinstance(updates, dict):
        return {}, []

    cleaned = {}
    errors = []

    if "time_of_day" in updates:
        value = str(updates.get("time_of_day", "")).strip().lower()
        if value in VALID_TIME_OF_DAY:
            cleaned["time_of_day"] = value

    if "day" in updates:
        day = updates.get("day")
        if isinstance(day, int) and not isinstance(day, bool) and day > 0:
            cleaned["day"] = day

    return cleaned, errors

def _sanitize_arc_update(raw_arc_update):
    cleaned = {"advance": False, "beat_id": "", "reason": ""}
    if raw_arc_update is None:
        raw_arc_update = {}
    if not isinstance(raw_arc_update, dict):
        return cleaned, []

    if isinstance(raw_arc_update.get("advance"), bool):
        cleaned["advance"] = raw_arc_update["advance"]
    cleaned["beat_id"] = _slugify(raw_arc_update.get("beat_id"))
    cleaned["reason"] = " ".join(str(raw_arc_update.get("reason", "")).strip().split())[:160]
    return cleaned, []

def _build_auto_narrator(current_location, current_npc, speaker_text, last_narrator=""):
    location = str(current_location or "current location").strip()
    speaker = str(speaker_text or current_npc or "Someone").strip() or "Someone"

    location_line = {
        "Market Gate": "Rain slicks the Market Gate while carts groan through the puddled dark.",
        "Old Library": "Stormwater taps through cracked glass as the Old Library settles into a tense hush.",
    }.get(location, f"The air stays tense around {location}.")

    speaker_line = {
        "Eli": "Eli keeps one shoulder angled toward the street, as if he expects trouble to come looking for him.",
        "Mara": "Mara waits by the archive desk with the stillness of someone already weighing the truth.",
    }.get(speaker, f"{speaker} watches you closely before answering.")

    candidate = f"{location_line} {speaker_line}".strip()
    previous = " ".join(str(last_narrator or "").strip().split())
    if not candidate:
        return ""
    # Reject the fallback if it would repeat exactly or if the previous
    # narrator already contains this stock line alongside story bridge text.
    if candidate == previous or candidate in previous:
        return ""
    return candidate

def _normalise_text_for_compare(value):
    return " ".join(str(value or "").strip().lower().split())

def _text_similarity_tokens(value):
    return {token for token in re.findall(r"[a-z0-9']+", _normalise_text_for_compare(value)) if len(token) >= 4}

def _is_too_similar_to_previous(current_text, previous_text):
    current = _normalise_text_for_compare(current_text)
    previous = _normalise_text_for_compare(previous_text)
    if not current or not previous:
        return False
    if current == previous:
        return True

    shorter = min(len(current), len(previous))
    if shorter >= 40 and (current in previous or previous in current):
        return True

    current_tokens = _text_similarity_tokens(current)
    previous_tokens = _text_similarity_tokens(previous)
    if not current_tokens or not previous_tokens:
        return False

    common = current_tokens & previous_tokens
    overlap_ratio = len(common) / max(1, min(len(current_tokens), len(previous_tokens)))
    return overlap_ratio >= 0.8 and len(common) >= 4

def _has_unsupported_scene_drift(text):
    low = _normalise_text_for_compare(text)
    if not low:
        return False
    return any(re.search(pattern, low) for pattern in UNSUPPORTED_SCENE_PATTERNS)

def _estimate_importance(event_type, state_updates, arc_update):
    score = 3
    if state_updates:
        score += 2
    if arc_update.get("advance"):
        score += 2
    if event_type in {"clue", "threat", "quest"}:
        score += 1
    return max(0, min(10, score))

def _validate_output(
    parsed,
    *,
    current_npc,
    current_location,
    current_player_choice,
    last_choices,
    story_suggestions,
    forced_choices,
    required_choice_count,
    world_state,
):
    if not isinstance(parsed, dict):
        return False, None, ["Output is not a JSON object."]

    errors = []
    narrator_text = parsed.get("narrator", "")
    if not isinstance(narrator_text, str):
        errors.append("Key 'narrator' must be str")
        narrator_text = ""
    narrator_text = narrator_text.strip()

    speaker_text = str(parsed.get("speaker", "")).strip()
    reply_text = str(parsed.get("reply", "")).strip()
    active_npc = str(current_npc or "").strip()
    current_choice_text = str(current_player_choice.get("text", "")).strip().lower()
    last_narrator = str(world_state.get("last_narrator", "")).strip()
    last_reply = str(world_state.get("last_reply", "")).strip()
    last_speaker = str(world_state.get("last_speaker", "")).strip()

    if not speaker_text or not reply_text:
        errors.append("Dialogue mode: speaker and reply must both be non-empty.")
    if active_npc and speaker_text.lower() != active_npc.lower():
        errors.append(f"Dialogue mode: speaker must be current_npc '{active_npc}'.")
    if current_choice_text and reply_text.lower() == current_choice_text:
        errors.append("Dialogue mode: reply must not repeat the player's selected line verbatim.")
    if (
        last_reply
        and last_speaker
        and active_npc
        and last_speaker.lower() == active_npc.lower()
        and _is_too_similar_to_previous(reply_text, last_reply)
    ):
        errors.append("Dialogue mode: reply must add new information, not paraphrase the previous NPC line.")
    if _has_unsupported_scene_drift(reply_text):
        errors.append("Dialogue mode: reply introduced unsupported scene details.")
    if narrator_text and _is_too_similar_to_previous(narrator_text, last_narrator):
        narrator_text = ""
    if narrator_text and _has_unsupported_scene_drift(narrator_text):
        narrator_text = ""
    if not narrator_text:
        narrator_text = _build_auto_narrator(
            current_location,
            current_npc,
            speaker_text or active_npc,
            last_narrator=last_narrator,
        )

    raw_choices = parsed.get("choices")
    if not isinstance(raw_choices, list):
        errors.append("Key 'choices' must be list")
        raw_choices = []

    cleaned_choices = []
    seen_choice_ids = set()
    for idx, raw_choice in enumerate(raw_choices[:MAX_LLM_CHOICES], start=1):
        choice = _normalise_choice(raw_choice, fallback_index=idx)
        if not choice:
            continue
        if _has_unsupported_scene_drift(choice.get("text", "")):
            continue
        key = _choice_key(choice)
        if key in seen_choice_ids:
            continue
        seen_choice_ids.add(key)
        cleaned_choices.append(choice)

    if forced_choices:
        cleaned_choices = _coerce_choice_list(forced_choices)[:required_choice_count]
    else:
        while len(cleaned_choices) < max(MIN_LLM_CHOICES, required_choice_count):
            progress = _build_progress_choice(
                {_choice_key(choice) for choice in cleaned_choices},
                current_npc=current_npc,
                current_location=current_location,
            )
            if _choice_key(progress) in {_choice_key(choice) for choice in cleaned_choices}:
                break
            cleaned_choices.append(progress)

        cleaned_choices = _enforce_progress_choice(
            cleaned_choices,
            last_choices,
            current_npc=current_npc,
            current_location=current_location,
        )
        cleaned_choices = _inject_story_choice(cleaned_choices, story_suggestions, last_choices)
        cleaned_choices = _replace_repeated_choices(
            cleaned_choices,
            last_choices,
            current_npc=current_npc,
            current_location=current_location,
        )
        while len(cleaned_choices) < required_choice_count:
            progress = _build_progress_choice(
                {_choice_key(choice) for choice in cleaned_choices},
                current_npc=current_npc,
                current_location=current_location,
            )
            if _choice_key(progress) in {_choice_key(choice) for choice in cleaned_choices}:
                break
            cleaned_choices.append(progress)

    cleaned_choices = cleaned_choices[:required_choice_count]
    if len(cleaned_choices) != required_choice_count:
        errors.append(f"choices must contain exactly {required_choice_count} items")

    cleaned_updates, update_errors = _sanitize_state_updates(parsed.get("state_updates", {}))
    errors.extend(update_errors)

    memory_summary = parsed.get("memory_summary", "")
    if not isinstance(memory_summary, str):
        memory_summary = ""
    memory_summary = memory_summary.strip()
    if not memory_summary:
        memory_summary = _build_auto_memory_summary(
            speaker_text,
            reply_text,
            current_npc=current_npc,
            current_location=current_location,
        )

    arc_update, arc_errors = _sanitize_arc_update(parsed.get("arc_update", {}))
    errors.extend(arc_errors)

    event_type = str(parsed.get("event_type", "dialogue")).strip().lower() or "dialogue"
    if event_type not in ALLOWED_EVENT_TYPES:
        event_type = "dialogue"

    raw_tags = parsed.get("tags", [])
    clean_tags = []
    if isinstance(raw_tags, list):
        for raw_tag in raw_tags:
            tag = _slugify(raw_tag)
            if tag and tag not in clean_tags:
                clean_tags.append(tag)
    if not clean_tags:
        clean_tags = _derive_tags(
            reply_text,
            memory_summary,
            current_npc,
            current_location,
            world_state.get("active_quests", {}),
        )

    raw_importance = parsed.get("importance")
    if isinstance(raw_importance, bool) or not isinstance(raw_importance, int):
        importance = _estimate_importance(event_type, cleaned_updates, arc_update)
    else:
        importance = max(0, min(10, raw_importance))

    if errors:
        return False, None, errors

    parsed["narrator"] = narrator_text
    parsed["speaker"] = speaker_text
    parsed["reply"] = reply_text
    parsed["choices"] = cleaned_choices
    parsed["state_updates"] = cleaned_updates
    parsed["memory_summary"] = memory_summary
    parsed["arc_update"] = arc_update
    parsed["event_type"] = event_type
    parsed["tags"] = clean_tags[:6]
    parsed["importance"] = importance
    return True, parsed, []

def _generate_valid_json(
    llm,
    prompt_text,
    *,
    current_npc,
    current_location,
    current_player_choice,
    last_choices,
    story_suggestions,
    forced_choices,
    required_choice_count,
    world_state,
    arc_state,
):
    base_messages = [
        {"role": "system", "content": "You are a grounded fantasy NPC narrator. Keep replies short and specific."},
        {"role": "user", "content": prompt_text},
    ]
    original_max_new_tokens = getattr(llm, "max_new_tokens", None)
    last_raw = ""
    last_errors = []

    try:
        for attempt in range(1, MAX_JSON_RETRY_ATTEMPTS + 1):
            attempt_messages = list(base_messages)
            if attempt == 2:
                forced_choice_hint = (
                    f"The only valid next choice is: {forced_choices[0]['text']}\n"
                    if forced_choices and len(forced_choices) == 1
                    else ""
                )
                repair_content = (
                    "Your last response was invalid. Return ONLY valid JSON.\n"
                    + f"Fix these errors exactly: {json.dumps(last_errors)}\n"
                    + f"Use this exact speaker value: {current_npc}\n"
                    + "Never set speaker to Alex.\n"
                    + f"Keep the reply in {current_npc}'s own voice and do not speak as another NPC.\n"
                    + f"Choices must be exactly {required_choice_count} object{'s' if required_choice_count != 1 else ''} with keys id, text, action_type.\n"
                    + forced_choice_hint
                    + "Do not change quest status, inventory, current_npc, or current_location in state_updates.\n"
                    + "No markdown fences. No explanation. JSON object only."
                )
                attempt_messages.append(
                    {
                        "role": "user",
                        "content": repair_content,
                    }
                )
            elif attempt == 3:
                choice_skeleton = (
                    "\"choices\":[{\"id\":\"choice_1\",\"text\":\"\",\"action_type\":\"ask\"}],"
                    if required_choice_count == 1
                    else "\"choices\":[{\"id\":\"choice_1\",\"text\":\"\",\"action_type\":\"ask\"},{\"id\":\"choice_2\",\"text\":\"\",\"action_type\":\"ask\"}],"
                )
                skeleton_content = (
                    "Reset and return the bare minimum valid JSON using this skeleton exactly.\n"
                    + "{"
                    + "\"narrator\":\"\","
                    + f"\"speaker\":\"{current_npc}\","
                    + "\"reply\":\"\","
                    + choice_skeleton
                    + "\"state_updates\":{},"
                    + "\"memory_summary\":\"\","
                    + "\"arc_update\":{\"advance\":false,\"beat_id\":\"\",\"reason\":\"\"},"
                    + "\"event_type\":\"dialogue\","
                    + "\"tags\":[],"
                    + "\"importance\":3"
                    + "}\n"
                    + "Fill the empty strings with short valid content only."
                )
                attempt_messages.append(
                    {
                        "role": "user",
                        "content": skeleton_content,
                    }
                )
            elif attempt == 4:
                if isinstance(original_max_new_tokens, int):
                    llm.max_new_tokens = max(64, min(original_max_new_tokens, 96))
                forced_choice_hint = (
                    f"The only valid next choice is: {forced_choices[0]['text']}\n"
                    if forced_choices and len(forced_choices) == 1
                    else ""
                )
                final_repair_content = (
                    "Final repair attempt. Keep everything extremely short.\n"
                    + f"Speaker must be exactly {current_npc}.\n"
                    + f"Reply must stay in {current_npc}'s voice.\n"
                    + f"Current beat: {arc_state.get('next_required_beat') or 'none'}.\n"
                    + "Use one short sentence for reply.\n"
                    + "Use at most one short sentence for narrator, or an empty string.\n"
                    + f"Choices must be exactly {required_choice_count} simple concrete next step{'s' if required_choice_count != 1 else ''}.\n"
                    + forced_choice_hint
                    + "Return only a valid JSON object."
                )
                attempt_messages.append(
                    {
                        "role": "user",
                        "content": final_repair_content,
                    }
                )

            raw = llm.generate(attempt_messages)
            last_raw = raw
            parsed = _extract_json_object(raw)
            valid, parsed_output, errors = _validate_output(
                parsed,
                current_npc=current_npc,
                current_location=current_location,
                current_player_choice=current_player_choice,
                last_choices=last_choices,
                story_suggestions=story_suggestions,
                forced_choices=forced_choices,
                required_choice_count=required_choice_count,
                world_state=world_state,
            )
            if valid:
                log_errors = []
                if attempt > 1:
                    log_errors.append(f"json_retry_attempt_{attempt}")
                return raw, parsed_output, log_errors
            last_errors = errors
    finally:
        if isinstance(original_max_new_tokens, int):
            llm.max_new_tokens = original_max_new_tokens

    raise OutputValidationExhausted(
        f"Model could not produce valid JSON after {MAX_JSON_RETRY_ATTEMPTS} attempts.",
        last_raw=last_raw,
        errors=[f"json_failed_after_{MAX_JSON_RETRY_ATTEMPTS}_attempts"] + list(last_errors),
        attempts=MAX_JSON_RETRY_ATTEMPTS,
    )
