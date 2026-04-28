'''
tests/test_story_rules.py
Unit stests for story rules, testing the deterministic logic only 
'''

from src.story_rules import (
    LEDGER_EVIDENCE,
    apply_story_choice,
    canonicalize_story_state,
    forced_story_choices,
    suggest_story_choices,
)

def test_canonicalize_story_state_repairs_corrupted_quest_status(): #If the quest is 'failed, then this should fix it back to being active
    state = canonicalize_story_state(
        {
            "active_quests": {"echo_shard": "failed"},
            "quest_flags": {"met_eli": False, "found_ledger_clue": False, "truth_reported": False},
            "inventory": [],
        }
    )

    assert state["active_quests"]["echo_shard"] == "active"

def test_story_rules_move_the_player_to_mara_and_secure_ledger_evidence(): #Testing the two steps in this mission
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
    assert inspect["quest_flags"]["found_eli_clue"] is True
    assert LEDGER_EVIDENCE in inspect["inventory_add"]
    assert inspect["narrator_lines"]

def test_story_rules_complete_the_case_after_reporting_to_mara(): # Once the player has a clue the flags, truth_reported and reported_eli_to_mara_
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
            "id": "report_eli_to_mara",
            "text": "Mara, the boot print and ledger point to Eli. He is our best suspect.",
            "action_type": "accuse",
        },
        current_npc="Mara",
        current_location="Old Library",
    )

    assert result["quest_flags"]["reported_eli_to_mara"] is True
    assert result["quest_flags"]["truth_reported"] is True
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

def test_forced_story_choices_always_returns_empty(): #Checking that I remove forced choices to keep player agency
    inspect_choices = forced_story_choices(
        {
            "quest_flags": {"met_eli": True, "found_ledger_clue": False, "truth_reported": False, "case_closed": False},
            "active_quests": {"echo_shard": "active"},
        },
        current_npc="Mara",
        current_location="Old Library",
    )
    assert inspect_choices == []

    close_choices = forced_story_choices(
        {
            "quest_flags": {"met_eli": True, "found_ledger_clue": True, "truth_reported": True, "case_closed": False},
            "active_quests": {"echo_shard": "completed"},
        },
        current_npc="Mara",
        current_location="Old Library",
    )
    assert close_choices == []

def test_close_case_marks_the_mission_finished(): #Final part of mission, requires all past flags to be set before ending the entire thing

    state = canonicalize_story_state(
        {
            "current_location": "Market Gate",
            "current_npc": "Eli",
            "quest_flags": {
                "met_eli": True,
                "found_ledger_clue": True,
                "found_eli_clue": True,
                "reported_eli_to_mara": True,
                "truth_reported": True,
                "case_closed": False,
            },
            "active_quests": {"echo_shard": "active"},
            "inventory": [LEDGER_EVIDENCE],
        }
    )

    result = apply_story_choice(
        state,
        {
            "id": "accuse_eli_with_mara",
            "text": "Eli, step away from the gate. Mara knows you tampered with the shipment.",
            "action_type": "accuse",
        },
        current_npc="Eli",
        current_location="Market Gate",
    )

    assert result["quest_flags"]["case_closed"] is True
    assert result["quest_flags"]["confronted_eli"] is True
    assert result["active_quests"]["echo_shard"] == "completed"
    assert "accuse_eli_with_mara" in result["applied_rules"]
