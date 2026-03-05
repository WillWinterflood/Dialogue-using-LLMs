'''
src/prologue.py

Hardcoded prologue scene and scripted choices, Removing the header saying prologue for when i show it to people
'''
import time
from src.text_fx import type_line
PROLOGUE_THOUGHT_SECONDS = 3

def run_prologue():
    print("### PROLOGUE (HARDCODED) ###")
    type_line(
        "Narrator: Rain needles through the crooked streets, turning dust to black sludge."
    )
    type_line(
        "Narrator: In this town, shutters close before sunset and debts outlive the people who owe them."
    )
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
    type_line("How do you answer Mara?")
    type_line("  1) I'm in. Tell me where to start.")
    type_line("  2) Why pick me for this?")

    while True:
        c1 = input("Choice > ").strip()
        if c1 in ("1", "2"):
            break
        print("Enter 1 or 2.")

    if c1 == "1":
        type_line("Alex: I'm in. Tell me where to start.")
        print("Mara is thinking.")
        time.sleep(PROLOGUE_THOUGHT_SECONDS)
        type_line("Mara: Good. Keep your head down and your ears open.")
    else:
        type_line("Alex: Why pick me for this?")
        print("Mara is thinking.")
        time.sleep(PROLOGUE_THOUGHT_SECONDS)
        type_line("Mara: Because you don't scare easy, and you still owe me a favor.")

    type_line("What is your first move?")
    type_line("  1) Go straight to Eli at the Market Gate.")
    type_line("  2) Check the library shipping records first.")

    while True:
        c2 = input("Choice > ").strip()
        if c2 in ("1", "2"):
            break
        print("Enter 1 or 2.")

    if c2 == "1":
        final_player_action = "I go to the Market Gate and question Eli about the missing shipment."
        current_npc = "Eli"
        current_location = "Market Gate"
        type_line("Alex: I'll go to the Market Gate and find Eli.")
        print("Mara is thinking.")
        time.sleep(PROLOGUE_THOUGHT_SECONDS)
        type_line("Mara: Ask short questions. Eli lies when people ramble.")
    else:
        final_player_action = "I inspect ledger 7C in the Old Library before meeting Eli."
        current_npc = "Mara"
        current_location = "Old Library"
        type_line("Alex: I'll check your shipping records first.")
        print("Mara is thinking.")
        time.sleep(PROLOGUE_THOUGHT_SECONDS)
        type_line("Mara: Fine. Find ledger 7C, then go to Eli with facts in hand.")

    type_line("Narrator: The scripted prologue ends. From here, dynamic mode continues.")
    print()

    prologue_summary = (
        "Prologue summary: Mara asked Alex to investigate the missing Echo Shard. "
        "Eli was last seen near the Market Gate. "
        "Player final scripted action: " + final_player_action
    )

    return prologue_summary, final_player_action, current_npc, current_location
