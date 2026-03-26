"""
/src/story_rules.py
Deterministic story rules. Game Logic

The LLM handles wording and flavour; this module protects canonical
scene/quest progression so the game can keep moving even when generation
is imperfect.
"""

CORE_QUEST_ID = "echo_shard"
LEDGER_EVIDENCE = "Ledger 7C copy"
BOOT_PRINT_EVIDENCE = "Boot print sketch"
DEFAULT_QUEST_FLAGS = {
    "met_eli": False,
    "found_ledger_clue": False,
    "found_eli_clue": False,
    "reported_eli_to_mara": False,
    "truth_reported": False,
    "confronted_eli": False,
    "case_closed": False,
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

    #Creating flags for checkpoints, this is to ensure that the LLM makes the story keep going forward and not sideways.
    if flags["found_ledger_clue"]:
        flags["found_eli_clue"] = True
    if flags["found_eli_clue"]:
        flags["found_ledger_clue"] = True
    if flags["reported_eli_to_mara"]:
        flags["truth_reported"] = True
    if flags["truth_reported"]:
        flags["reported_eli_to_mara"] = True
    if flags["confronted_eli"]:
        flags["case_closed"] = True
    if flags["case_closed"]:
        flags["confronted_eli"] = True

    out["quest_flags"] = flags

    raw_quests = out.get("active_quests", {})
    active_quests = dict(raw_quests) if isinstance(raw_quests, dict) else {}
    active_quests[CORE_QUEST_ID] = "completed" if flags["case_closed"] else "active"
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
        seen.add(LEDGER_EVIDENCE.lower())
    if flags["found_eli_clue"] and BOOT_PRINT_EVIDENCE.lower() not in seen:
        cleaned_inventory.append(BOOT_PRINT_EVIDENCE)
    out["inventory"] = cleaned_inventory
    return out

def suggest_story_choices(world_state, current_npc, current_location):
    state = canonicalize_story_state(world_state)
    flags = state.get("quest_flags", {})
    npc = str(current_npc or "").strip()
    location = str(current_location or "").strip()

    if flags.get("case_closed"):
        return []

    suggestions = []
    if location == "Market Gate" and npc == "Eli" and not flags.get("found_eli_clue"):
        suggestions.append(
            {
                "id": "ask_eli_about_route_entry",
                "text": "Eli, who changed the route entry?",
                "action_type": "ask",
            }
        )
        suggestions.append(
            {
                "id": "travel_old_library",
                "text": "I should inspect ledger 7C in the Old Library.",
                "action_type": "travel",
            }
        )
    if location == "Old Library" and npc == "Mara" and not flags.get("found_eli_clue"):
        suggestions.append(
            {
                "id": "inspect_ledger_7c",
                "text": "Mara, show me ledger 7C and the archive floor around it.",
                "action_type": "investigate",
            }
        )
    if flags.get("found_eli_clue") and not flags.get("reported_eli_to_mara"):
        if location == "Old Library" and npc == "Mara":
            suggestions.append(
                {
                    "id": "report_eli_to_mara",
                    "text": "Mara, the boot print and ledger point to Eli. He is our best suspect.",
                    "action_type": "accuse",
                }
            )
        else:
            suggestions.append(
                {
                    "id": "report_to_mara",
                    "text": "I should take this clue back to Mara.",
                    "action_type": "travel",
                }
            )
    if flags.get("reported_eli_to_mara") and not flags.get("case_closed"):
        if location == "Old Library" and npc == "Mara":
            suggestions.append(
                {
                    "id": "confront_eli_with_mara",
                    "text": "Mara, come with me. We confront Eli at the Market Gate now.",
                    "action_type": "travel",
                }
            )
        elif location == "Market Gate" and npc == "Eli":
            suggestions.append(
                {
                    "id": "accuse_eli_with_mara",
                    "text": "Eli, step away from the gate. Mara knows you tampered with the shipment.",
                    "action_type": "accuse",
                }
            )
    return suggestions


def forced_story_choices(world_state, current_npc, current_location):
    state = canonicalize_story_state(world_state)
    flags = state.get("quest_flags", {})
    npc = str(current_npc or "").strip()
    location = str(current_location or "").strip()

    if flags.get("case_closed"):
        return []
    if location == "Old Library" and npc == "Mara" and not flags.get("found_eli_clue"):
        return [
            {
                "id": "inspect_ledger_7c",
                "text": "Mara, show me ledger 7C and the archive floor around it.",
                "action_type": "investigate",
            }
        ]
    if location == "Old Library" and npc == "Mara" and flags.get("found_eli_clue") and not flags.get("reported_eli_to_mara"):
        return [
            {
                "id": "report_eli_to_mara",
                "text": "Mara, the boot print and ledger point to Eli. He is our best suspect.",
                "action_type": "accuse",
            }
        ]
    if location == "Old Library" and npc == "Mara" and flags.get("reported_eli_to_mara") and not flags.get("case_closed"):
        return [
            {
                "id": "confront_eli_with_mara",
                "text": "Mara, come with me. We confront Eli at the Market Gate now.",
                "action_type": "travel",
            }
        ]
    if location == "Market Gate" and npc == "Eli" and flags.get("reported_eli_to_mara") and not flags.get("case_closed"):
        return [
            {
                "id": "accuse_eli_with_mara",
                "text": "Eli, step away from the gate. Mara knows you tampered with the shipment.",
                "action_type": "accuse",
            }
        ]
    return []


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
        "narrator_lines": [],
    }

    interactive_actions = {"ask", "investigate", "accuse", "reassure", "threaten", "trade", "resume"}
    if effects["current_npc"] == "Eli" and action_type in interactive_actions and not flags.get("met_eli"):
        effects["quest_flags"]["met_eli"] = True
        effects["applied_rules"].append("met_eli")
        effects["narrator_lines"].append(
            "Eli lingers beneath the Market Gate awning, speaking low while wagons grind past in the rain."
        )

    travel_to_library = (
        choice_id in {"travel_old_library", "report_to_mara"}
        or (
            action_type == "travel"
            and _has_any(
                choice_text,
                (
                    "old library",
                    "back to mara",
                    "report to mara",
                    "take this clue back to mara",
                ),
            )
        )
    )
    if travel_to_library:
        effects["current_location"] = "Old Library"
        effects["current_npc"] = "Mara"
        effects["known_locations"].append("Old Library")
        effects["applied_rules"].append("travel_old_library")
        effects["narrator_lines"].append(
            "You leave the Market Gate behind and cut back through the rain to the Old Library, where Mara waits beneath cracked glass."
        )

    effective_location = effects["current_location"] or str(current_location or "").strip()
    effective_npc = effects["current_npc"] or str(current_npc or "").strip()
    effective_flags = dict(flags)
    effective_flags.update(effects["quest_flags"])

    inspects_ledger = (
        effective_location == "Old Library"
        and effective_npc == "Mara"
        and not effective_flags.get("found_eli_clue")
        and (
            choice_id == "inspect_ledger_7c"
            or (
                action_type == "investigate"
                and _has_any(choice_text, ("ledger 7c", "archive floor", "archive seal", "boot print", "tampered ledger"))
            )
        )
    )
    if inspects_ledger:
        effects["quest_flags"]["found_ledger_clue"] = True
        effects["quest_flags"]["found_eli_clue"] = True
        effects["inventory_add"].extend([LEDGER_EVIDENCE, BOOT_PRINT_EVIDENCE])
        effects["milestones"].append("find_clue_pointing_to_eli")
        effects["applied_rules"].append("inspect_ledger_7c")
        effective_flags["found_ledger_clue"] = True
        effective_flags["found_eli_clue"] = True
        effects["narrator_lines"].append(
            "Mara spreads ledger 7C across the archive desk. A muddy split-heel boot print cuts across the floor beside it, stamped in the same red gate-mud clinging to Eli's boots."
        )

    reports_eli = (
        effective_location == "Old Library"
        and effective_npc == "Mara"
        and effective_flags.get("found_eli_clue")
        and not effective_flags.get("reported_eli_to_mara")
        and (
            choice_id == "report_eli_to_mara"
            or _has_any(
                choice_text,
                (
                    "eli is our best suspect",
                    "point to eli",
                    "boot print and ledger",
                    "eli tampered",
                    "eli did it",
                ),
            )
        )
    )
    if reports_eli:
        effects["quest_flags"]["reported_eli_to_mara"] = True
        effects["quest_flags"]["truth_reported"] = True
        effects["milestones"].append("report_eli_to_mara")
        effects["applied_rules"].append("report_eli_to_mara")
        effective_flags["reported_eli_to_mara"] = True
        effects["narrator_lines"].append(
            "You lay the copied ledger beside the boot print sketch. Mara studies them in silence, then gives a single hard nod when Eli's name becomes unavoidable."
        )

    travel_to_confront = (
        effective_location == "Old Library"
        and effective_npc == "Mara"
        and effective_flags.get("reported_eli_to_mara")
        and not effective_flags.get("case_closed")
        and (
            choice_id == "confront_eli_with_mara"
            or (
                action_type == "travel"
                and _has_any(
                    choice_text,
                    (
                        "confront eli",
                        "market gate now",
                        "come with me",
                        "we confront eli",
                    ),
                )
            )
        )
    )
    if travel_to_confront:
        effects["current_location"] = "Market Gate"
        effects["current_npc"] = "Eli"
        effects["known_locations"].append("Market Gate")
        effects["applied_rules"].append("travel_market_gate_for_confrontation")
        effects["narrator_lines"].append(
            "Mara comes with you through the rain to the Market Gate, one hand already resting on the warrant chain at her belt."
        )
        effective_location = "Market Gate"
        effective_npc = "Eli"

    confronts_eli = (
        effective_location == "Market Gate"
        and effective_npc == "Eli"
        and effective_flags.get("reported_eli_to_mara")
        and not effective_flags.get("case_closed")
        and (
            choice_id == "accuse_eli_with_mara"
            or action_type == "accuse"
            or _has_any(
                choice_text,
                (
                    "mara knows",
                    "step away from the gate",
                    "tampered with the shipment",
                    "eli, you changed the route entry",
                ),
            )
        )
    )
    if confronts_eli:
        effects["quest_flags"]["confronted_eli"] = True
        effects["quest_flags"]["case_closed"] = True
        effects["active_quests"][CORE_QUEST_ID] = "completed"
        effects["npc_relationships"]["Mara"] = 2
        effects["npc_relationships"]["Eli"] = -3
        effects["milestones"].append("confront_eli_with_mara")
        effects["applied_rules"].append("accuse_eli_with_mara")
        effects["narrator_lines"].append(
            "Mara steps in beside you before Eli can bolt. Under the weight of the ledger and the boot print, he folds, and the town watch closes around him."
        )
    else:
        effects["active_quests"].setdefault(CORE_QUEST_ID, "active")

    return effects
