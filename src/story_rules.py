"""
/src/story_rules.py
Deterministic story rules.

The LLM handles wording and flavour; this module protects canonical
scene/quest progression so the game can keep moving even when generation
is imperfect.
"""

CORE_QUEST_ID = "echo_shard"
LEDGER_EVIDENCE = "Ledger 7C copy"
DEFAULT_QUEST_FLAGS = {
    "met_eli": False,
    "found_ledger_clue": False,
    "truth_reported": False,
}


def _normalize_text(value):
    return " ".join(str(value or "").strip().lower().split())


def _has_any(text, needles):
    return any(needle in text for needle in needles)


def _normalize_choice(choice):
    if not isinstance(choice, dict):
        return {"id": "", "text": _normalize_text(choice), "action_type": ""}
    return {
        "id": _normalize_text(choice.get("id")),
        "text": _normalize_text(choice.get("text")),
        "action_type": _normalize_text(choice.get("action_type")),
    }


def canonicalize_story_state(state):
    if not isinstance(state, dict):
        return {}

    out = dict(state)

    raw_flags = out.get("quest_flags", {})
    flags = dict(DEFAULT_QUEST_FLAGS)
    if isinstance(raw_flags, dict):
        for key in DEFAULT_QUEST_FLAGS:
            value = raw_flags.get(key)
            if isinstance(value, bool):
                flags[key] = value
    out["quest_flags"] = flags

    raw_quests = out.get("active_quests", {})
    active_quests = dict(raw_quests) if isinstance(raw_quests, dict) else {}
    active_quests[CORE_QUEST_ID] = "completed" if flags["truth_reported"] else "active"
    out["active_quests"] = active_quests

    inventory = out.get("inventory", [])
    if not isinstance(inventory, list):
        inventory = []
    cleaned_inventory = []
    seen = set()
    for item in inventory:
        text = str(item).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned_inventory.append(text)
    if flags["found_ledger_clue"] and LEDGER_EVIDENCE.lower() not in seen:
        cleaned_inventory.append(LEDGER_EVIDENCE)
    out["inventory"] = cleaned_inventory
    return out


def suggest_story_choices(world_state, current_npc, current_location):
    state = canonicalize_story_state(world_state)
    flags = state.get("quest_flags", {})
    npc = str(current_npc or "").strip()
    location = str(current_location or "").strip()

    suggestions = []
    if location == "Market Gate" and npc == "Eli" and not flags.get("met_eli"):
        suggestions.append(
            {
                "id": "ask_eli_about_reroute",
                "text": "Eli, who ordered the reroute?",
                "action_type": "ask",
            }
        )
    if location == "Market Gate" and not flags.get("found_ledger_clue"):
        suggestions.append(
            {
                "id": "travel_old_library",
                "text": "I should inspect ledger 7C in the Old Library.",
                "action_type": "travel",
            }
        )
    if location == "Old Library" and not flags.get("found_ledger_clue"):
        suggestions.append(
            {
                "id": "inspect_ledger_7c",
                "text": "Mara, show me ledger 7C and the archive seals.",
                "action_type": "investigate",
            }
        )
    if flags.get("found_ledger_clue") and npc != "Mara":
        suggestions.append(
            {
                "id": "report_to_mara",
                "text": "I should take this evidence back to Mara.",
                "action_type": "travel",
            }
        )
    if location == "Old Library" and npc == "Mara" and flags.get("found_ledger_clue") and not flags.get("truth_reported"):
        suggestions.append(
            {
                "id": "report_truth_to_mara",
                "text": "Mara, the ledger was tampered with. Here is what I found.",
                "action_type": "ask",
            }
        )
    if flags.get("truth_reported"):
        suggestions.append(
            {
                "id": "close_case",
                "text": "I have what I need. Let's close the case for now.",
                "action_type": "exit",
            }
        )
    return suggestions


def apply_story_choice(world_state, player_choice, current_npc, current_location):
    state = canonicalize_story_state(world_state)
    flags = dict(state.get("quest_flags", {}))
    choice = _normalize_choice(player_choice)
    choice_id = choice["id"]
    choice_text = choice["text"]
    action_type = choice["action_type"]

    effects = {
        "current_npc": str(current_npc or "").strip(),
        "current_location": str(current_location or "").strip(),
        "known_locations": [],
        "quest_flags": {},
        "active_quests": {},
        "inventory_add": [],
        "inventory_remove": [],
        "npc_relationships": {},
        "milestones": [],
        "applied_rules": [],
    }

    interactive_actions = {"ask", "investigate", "accuse", "reassure", "threaten", "trade", "resume"}
    if effects["current_npc"] == "Eli" and action_type in interactive_actions and not flags.get("met_eli"):
        effects["quest_flags"]["met_eli"] = True
        effects["milestones"].append("met_eli")
        effects["applied_rules"].append("met_eli")

    travel_to_library = (
        choice_id in {"travel_old_library", "report_to_mara"}
        or (
            action_type in {"travel", "investigate"}
            and _has_any(choice_text, ("old library", "ledger 7c", "mara"))
        )
    )
    if travel_to_library:
        effects["current_location"] = "Old Library"
        effects["current_npc"] = "Mara"
        effects["known_locations"].append("Old Library")
        effects["applied_rules"].append("travel_old_library")

    effective_location = effects["current_location"] or str(current_location or "").strip()
    effective_npc = effects["current_npc"] or str(current_npc or "").strip()
    effective_flags = dict(flags)
    effective_flags.update(effects["quest_flags"])

    inspects_ledger = (
        effective_location == "Old Library"
        and effective_npc == "Mara"
        and not effective_flags.get("found_ledger_clue")
        and (
            choice_id == "inspect_ledger_7c"
            or _has_any(choice_text, ("ledger 7c", "archive seal", "tampered ledger"))
        )
    )
    if inspects_ledger:
        effects["quest_flags"]["found_ledger_clue"] = True
        effects["inventory_add"].append(LEDGER_EVIDENCE)
        effects["milestones"].append("found_ledger_clue")
        effects["applied_rules"].append("inspect_ledger_7c")
        effective_flags["found_ledger_clue"] = True

    reports_truth = (
        effective_location == "Old Library"
        and effective_npc == "Mara"
        and effective_flags.get("found_ledger_clue")
        and not effective_flags.get("truth_reported")
        and (
            choice_id == "report_truth_to_mara"
            or _has_any(
                choice_text,
                (
                    "ledger was tampered",
                    "here is what i found",
                    "take this evidence",
                    "report back",
                ),
            )
        )
    )
    if reports_truth:
        effects["quest_flags"]["truth_reported"] = True
        effects["active_quests"][CORE_QUEST_ID] = "completed"
        effects["milestones"].append("truth_reported")
        effects["applied_rules"].append("report_truth_to_mara")
    else:
        effects["active_quests"][CORE_QUEST_ID] = "active"

    return effects
