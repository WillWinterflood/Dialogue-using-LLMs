from src.story_rules import (
    LEDGER_EVIDENCE,
    apply_story_choice,
    canonicalize_story_state,
    forced_story_choices,
    suggest_story_choices,
)


def test_canonicalize_story_state_repairs_corrupted_quest_status():
    state = canonicalize_story_state(
        {
            "active_quests": {"echo_shard": "failed"},
            "quest_flags": {"met_eli": False, "found_ledger_clue": False, "truth_reported": False},
            "inventory": [],
        }
    )

    assert state["active_quests"]["echo_shard"] == "active"


def test_story_rules_move_the_player_to_mara_and_secure_ledger_evidence():
    base_state = canonicalize_story_state(
        {
            "current_location": "Market Gate",
            "current_npc": "Eli",
            "quest_flags": {"met_eli": False, "found_ledger_clue": False, "truth_reported": False},
            "active_quests": {"echo_shard": "active"},
            "inventory": [],
        }
    )

    travel = apply_story_choice(
        base_state,
        {"id": "travel_old_library", "text": "I should inspect ledger 7C in the Old Library.", "action_type": "travel"},
        current_npc="Eli",
        current_location="Market Gate",
    )
    assert travel["current_location"] == "Old Library"
    assert travel["current_npc"] == "Mara"
    assert travel["narrator_lines"]

    library_state = canonicalize_story_state(
        {
            **base_state,
            "current_location": "Old Library",
            "current_npc": "Mara",
        }
    )
    inspect = apply_story_choice(
        library_state,
        {"id": "inspect_ledger_7c", "text": "Mara, show me ledger 7C and the archive seals.", "action_type": "investigate"},
        current_npc="Mara",
        current_location="Old Library",
    )

    assert inspect["quest_flags"]["found_ledger_clue"] is True
    assert inspect["quest_flags"]["truth_reported"] is True
    assert inspect["active_quests"]["echo_shard"] == "completed"
    assert LEDGER_EVIDENCE in inspect["inventory_add"]
    assert inspect["narrator_lines"]


def test_story_rules_complete_the_case_after_reporting_to_mara():
    state = canonicalize_story_state(
        {
            "current_location": "Old Library",
            "current_npc": "Mara",
            "quest_flags": {"met_eli": True, "found_ledger_clue": True, "truth_reported": False},
            "active_quests": {"echo_shard": "active"},
            "inventory": [LEDGER_EVIDENCE],
        }
    )

    result = apply_story_choice(
        state,
        {
            "id": "report_truth_to_mara",
            "text": "Mara, the ledger was tampered with. Here is what I found.",
            "action_type": "ask",
        },
        current_npc="Mara",
        current_location="Old Library",
    )

    assert result["quest_flags"]["truth_reported"] is True
    assert result["active_quests"]["echo_shard"] == "completed"
    assert result["narrator_lines"]


def test_market_gate_ledger_question_does_not_force_scene_jump_to_mara():
    state = canonicalize_story_state(
        {
            "current_location": "Market Gate",
            "current_npc": "Eli",
            "quest_flags": {"met_eli": True, "found_ledger_clue": False, "truth_reported": False},
            "active_quests": {"echo_shard": "active"},
            "inventory": [],
        }
    )

    result = apply_story_choice(
        state,
        {
            "id": "investigate_ledger",
            "text": "Let's check ledger 7C first.",
            "action_type": "investigate",
        },
        current_npc="Eli",
        current_location="Market Gate",
    )

    assert result["current_location"] == "Market Gate"
    assert result["current_npc"] == "Eli"
    assert result["quest_flags"] == {}


def test_suggest_story_choices_offers_a_directed_progress_option():
    choices = suggest_story_choices(
        {
            "quest_flags": {"met_eli": False, "found_ledger_clue": False, "truth_reported": False, "case_closed": False},
            "active_quests": {"echo_shard": "active"},
        },
        current_npc="Eli",
        current_location="Market Gate",
    )

    choice_ids = {choice["id"] for choice in choices}
    assert "travel_old_library" in choice_ids


def test_forced_story_choices_only_lock_ledger_inspection():
    inspect_choices = forced_story_choices(
        {
            "quest_flags": {"met_eli": True, "found_ledger_clue": False, "truth_reported": False, "case_closed": False},
            "active_quests": {"echo_shard": "active"},
        },
        current_npc="Mara",
        current_location="Old Library",
    )
    assert [choice["id"] for choice in inspect_choices] == ["inspect_ledger_7c"]

    close_choices = forced_story_choices(
        {
            "quest_flags": {"met_eli": True, "found_ledger_clue": True, "truth_reported": True, "case_closed": False},
            "active_quests": {"echo_shard": "completed"},
        },
        current_npc="Mara",
        current_location="Old Library",
    )
    assert close_choices == []


def test_close_case_marks_the_mission_finished():
    state = canonicalize_story_state(
        {
            "current_location": "Old Library",
            "current_npc": "Mara",
            "quest_flags": {"met_eli": True, "found_ledger_clue": True, "truth_reported": True, "case_closed": False},
            "active_quests": {"echo_shard": "completed"},
            "inventory": [LEDGER_EVIDENCE],
        }
    )

    result = apply_story_choice(
        state,
        {
            "id": "close_case",
            "text": "I have what I need. Let's close the case for now.",
            "action_type": "exit",
        },
        current_npc="Mara",
        current_location="Old Library",
    )

    assert result["quest_flags"]["case_closed"] is True
    assert "close_case" in result["applied_rules"]
