'''
/src/choice_formatter.py

This is to ensure the players choices are actually usable before they get shown on screen.
'''

import re
from src.config import ALLOWED_ACTION_TYPES, GENERIC_LOOP_MARKERS, MAX_LLM_CHOICES

def _slugify(text): #Turning messy label into a tidy tag, making it easier to understand
    value = re.sub(r"[^a-z0-9]+", "_", str(text or "").strip().lower())
    value = re.sub(r"_+", "_", value).strip("_")
    return value

#Cleaning the words
def _normalise_choice_text(raw_text): 
    text = str(raw_text or "").strip()
    if not text:
        return ""
    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        text = text[1:-1].strip()
    if not text:
        return ""

    text = " ".join(text.split())
    low = text.lower()
    malformed = ("i tell ", "i show ", "i give ", "i ask ", "i check ", "i look ", "i search ", "i explain ")
    if low.startswith(malformed):
        parts = text.split(maxsplit=2)
        if len(parts) >= 2:
            verb = parts[1].capitalize()
            rest = parts[2] if len(parts) >= 3 else ""
            text = f"{verb} {rest}".strip()

    if text and text[-1] not in ".!?":
        text += "."
    return text

def _normalise_choice(raw_choice, fallback_index=0):
    if isinstance(raw_choice, dict):
        text = raw_choice.get("text") or raw_choice.get("label") or raw_choice.get("utterance")
        choice_id = raw_choice.get("id")
        action_type = str(raw_choice.get("action_type", "ask")).strip().lower() or "ask"
    else:
        text = raw_choice
        choice_id = ""
        action_type = "ask"

    clean_text = _normalise_choice_text(text)
    if not clean_text:
        return None

    clean_id = _slugify(choice_id or clean_text)
    if not clean_id:
        clean_id = f"choice_{fallback_index or 1}"
    if action_type not in ALLOWED_ACTION_TYPES:
        action_type = "ask"
    return {"id": clean_id, "text": clean_text, "action_type": action_type}

def _coerce_choice_list(raw_choices):
    #Turning whatever list of choices comes in into a clean normalised list, capped at MAX_LLM_CHOICES
    cleaned = []
    for idx, raw_choice in enumerate(raw_choices or [], start=1):
        choice = _normalise_choice(raw_choice, fallback_index=idx)
        if choice:
            cleaned.append(choice)
        if len(cleaned) >= MAX_LLM_CHOICES:
            break
    return cleaned

#Gets a stable key for comparing choices, usually the ID. Needed to see whether a choice is getting reused.
def _choice_key(choice):
    if isinstance(choice, dict):
        return str(choice.get("id", "")).strip().lower()
    return _slugify(choice)

def _choice_text(choice):
    if isinstance(choice, dict):
        return str(choice.get("text", "")).strip()
    return _normalise_choice_text(choice)

def _is_generic_loop_choice(choice):
    #Detecting vague filler choices like "anything else?" that dont actually move the story forward
    low = _choice_text(choice).lower()
    return any(marker in low for marker in GENERIC_LOOP_MARKERS)

#If there is a halt with the progress then insert one of these candidates, could work but also could be repetitive...
def _build_progress_choice(blocked_keys, current_npc="", current_location=""):
    npc = str(current_npc or "").strip()
    location = str(current_location or "").strip()
    candidates = [
        {"text": "Give me one concrete lead I can verify right now.", "action_type": "ask"},
        {"text": "Who can confirm your version of events?", "action_type": "ask"},
        {"text": "What evidence can I check right now?", "action_type": "investigate"},
        {"text": "Where exactly should I investigate next?", "action_type": "travel"},
    ]
    if location:
        candidates.insert(1, {"text": f"Where in {location} should I investigate next?", "action_type": "travel"})
    if npc:
        candidates.insert(2, {"text": f"{npc}, name one person I should question next.", "action_type": "ask"})

    for idx, candidate in enumerate(candidates, start=1):
        choice = _normalise_choice(
            {
                "id": _slugify(candidate["text"]),
                "text": candidate["text"],
                "action_type": candidate["action_type"],
            },
            fallback_index=idx,
        )
        key = _choice_key(choice)
        if key and key not in blocked_keys:
            return choice
    return {
        "id": "ask_for_concrete_lead",
        "text": "Give me one concrete lead I can verify right now.",
        "action_type": "ask",
    }

def _enforce_progress_choice(cleaned_choices, last_choices, current_npc="", current_location=""):
    #If the player keeps getting the same choices, swap one out for something that pushes the investigation forward
    if not cleaned_choices:
        return cleaned_choices

    previous_keys = {_choice_key(choice) for choice in last_choices if _choice_key(choice)}
    current_keys = [_choice_key(choice) for choice in cleaned_choices]
    repeated_count = sum(1 for key in current_keys if key in previous_keys)
    all_generic = all(_is_generic_loop_choice(choice) for choice in cleaned_choices)
    looping = bool(previous_keys) and (repeated_count == len(cleaned_choices) or (repeated_count >= 1 and all_generic))
    if not looping:
        return cleaned_choices

    progress = _build_progress_choice(set(current_keys) | previous_keys, current_npc=current_npc, current_location=current_location)
    if len(cleaned_choices) == 1:
        return [cleaned_choices[0], progress]
    cleaned_choices[-1] = progress
    return cleaned_choices

def _replace_repeated_choices(cleaned_choices, last_choices, current_npc="", current_location=""):
    if not cleaned_choices:
        return cleaned_choices

    previous_keys = {_choice_key(choice) for choice in last_choices if _choice_key(choice)}
    
    if not previous_keys:
        return cleaned_choices

    refreshed = []
    used_keys = set()
    blocked_keys = set(previous_keys)

    for choice in cleaned_choices:
        candidate = choice
        candidate_key = _choice_key(candidate)
        if candidate_key in previous_keys:
            replacement = _build_progress_choice(
                blocked_keys | used_keys,
                current_npc=current_npc,
                current_location=current_location,
            )
            replacement_key = _choice_key(replacement)
            if replacement_key and replacement_key not in blocked_keys and replacement_key not in used_keys:
                candidate = replacement
                candidate_key = replacement_key

        if candidate_key and candidate_key not in used_keys:
            refreshed.append(candidate)
            used_keys.add(candidate_key)

    return refreshed

def _inject_story_choice(cleaned_choices, story_suggestions, last_choices):
    #Injecting a story-suggested choice into the list, replacing a generic one if there is no room
    if not story_suggestions:
        return cleaned_choices

    existing_keys = {_choice_key(choice) for choice in cleaned_choices if _choice_key(choice)}
    previous_keys = {_choice_key(choice) for choice in last_choices if _choice_key(choice)}

    for suggestion in story_suggestions:
        choice = _normalise_choice(suggestion, fallback_index=len(cleaned_choices) + 1)
        if not choice:
            continue

        key = _choice_key(choice)
        if not key or key in existing_keys:
            continue

        if len(cleaned_choices) < MAX_LLM_CHOICES:
            cleaned_choices.append(choice)
            return cleaned_choices

        replace_index = None
        for idx in range(len(cleaned_choices) - 1, -1, -1):
            candidate = cleaned_choices[idx]
            candidate_key = _choice_key(candidate)
            if _is_generic_loop_choice(candidate) or candidate_key in previous_keys:
                replace_index = idx
                break
        if replace_index is None:
            replace_index = len(cleaned_choices) - 1
        cleaned_choices[replace_index] = choice
        return cleaned_choices

    return cleaned_choices
