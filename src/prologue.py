'''
src/prologue.py

Hardcoded prologue scene and scripted choices, Removing the header saying prologue for when i show it to people
'''
import time
from src.text_fx import type_line
PROLOGUE_THOUGHT_SECONDS = 3

INTRO_RESPONSE_CHOICES = [
    {
        "id": "accept_case",
        "text": "I'm in. Tell me where to start.",
        "scene_reply": "Mara: Good. Keep your head down and your ears open.",
        "memory_summary": "Alex accepted Mara's job to recover the missing Echo Shard.",
    },
    {
        "id": "ask_why_me",
        "text": "Why pick me for this?",
        "scene_reply": "Mara: Because you don't scare easy, and you still owe me a favor.",
        "memory_summary": "Alex questioned why Mara chose him for the investigation.",
    },
]

FIRST_MOVE_CHOICES = [
    {
        "id": "go_to_market_gate",
        "menu_text": "Go straight to Eli at the Market Gate.",
        "spoken_text": "I'll go to the Market Gate and find Eli.",
        "scene_reply": "Mara: Ask short questions. Eli lies when people ramble.",
        "player_action_text": "I go to the Market Gate and question Eli about the missing shipment.",
        "current_npc": "Eli",
        "current_location": "Market Gate",
        "memory_summary": "Alex chose to go directly to Eli at the Market Gate.",
        "action_type": "travel",
    },
    {
        "id": "check_shipping_records",
        "menu_text": "Check the library shipping records first.",
        "spoken_text": "I'll check your shipping records first.",
        "scene_reply": "Mara: Fine. Find ledger 7C, then go to Eli with facts in hand.",
        "player_action_text": "I inspect ledger 7C in the Old Library before meeting Eli.",
        "current_npc": "Mara",
        "current_location": "Old Library",
        "memory_summary": "Alex chose to inspect the library shipping records before meeting Eli.",
        "action_type": "investigate",
    },
]


def _select_scripted_choice(prompt_text, options, display_key="text"):
    type_line(prompt_text)
    for idx, option in enumerate(options, start=1):
        type_line(f"  {idx}) {option[display_key]}")

    while True:
        raw = input("Choice > ").strip()
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1]
        print(f"Enter a number from 1 to {len(options)}.")

def run_prologue():
    print("### PROLOGUE (HARDCODED) ###")
    type_line(
        "Narrator: You left for an apprenticeship and came back to find familiar faces harder, poorer, and scared."
    )
    type_line(
        "Narrator: Mara's message reached you at dawn: return to the Old Library now, no questions."
    )
    type_line(
        "Narrator: By nightfall you're standing under cracked glass while stormwater drips through the rafters."
    )
    type_line("Mara: Alex. Good. The archive's Echo Shard is missing.")
    type_line("Alex: Missing? Who had access?")
    type_line("Mara: A courier team. Eli was last seen near the Market Gate. Start there.")
    type_line("Mara: Get me the truth.")
    print()

    print("### SCRIPTED CHOICES ###")
    scripted_events = []

    first_choice = _select_scripted_choice("How do you answer Mara?", INTRO_RESPONSE_CHOICES)
    type_line(f"Alex: {first_choice['text']}")
    print("Mara is thinking.")
    time.sleep(PROLOGUE_THOUGHT_SECONDS)
    type_line(first_choice["scene_reply"])
    scripted_events.append(
        {
            "mode": "scripted",
            "scene_id": "mara_intro_response",
            "choice_id": first_choice["id"],
            "choice_text": first_choice["text"],
            "memory_summary": first_choice["memory_summary"],
            "event_type": "prologue",
            "importance": 3,
            "tags": ["prologue", "mara", "echo_shard"],
            "quest_ids": ["echo_shard"],
            "current_npc": "Mara",
            "current_location": "Old Library",
        }
    )

    second_choice = _select_scripted_choice("What is your first move?", FIRST_MOVE_CHOICES, display_key="menu_text")
    type_line(f"Alex: {second_choice['spoken_text']}")
    print("Mara is thinking.")
    time.sleep(PROLOGUE_THOUGHT_SECONDS)
    type_line(second_choice["scene_reply"])
    scripted_events.append(
        {
            "mode": "scripted",
            "scene_id": "first_investigation_move",
            "choice_id": second_choice["id"],
            "choice_text": second_choice["player_action_text"],
            "memory_summary": second_choice["memory_summary"],
            "event_type": "handoff",
            "importance": 5,
            "tags": ["handoff", "investigation", second_choice["current_location"].lower().replace(" ", "_")],
            "quest_ids": ["echo_shard"],
            "current_npc": second_choice["current_npc"],
            "current_location": second_choice["current_location"],
            "action_type": second_choice["action_type"],
        }
    )

    type_line("Narrator: The scripted prologue ends. From here, dynamic mode continues.")
    print()

    prologue_summary = (
        "Prologue summary: Mara asked Alex to investigate the missing Echo Shard. "
        "Eli was last seen near the Market Gate. "
        "Player final scripted action: " + second_choice["player_action_text"]
    )

    handoff = {
        "first_choice_id": second_choice["id"],
        "first_action_text": second_choice["player_action_text"],
        "first_action_type": second_choice["action_type"],
        "current_npc": second_choice["current_npc"],
        "current_location": second_choice["current_location"],
        "handoff_turn_index": len(scripted_events),
        "scripted_events": scripted_events,
    }

    return prologue_summary, handoff
