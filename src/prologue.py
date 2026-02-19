'''
src/prologue.py

Hardcoded prologue scene and scripted choices
Prologue for now.. maybe expand later.
'''


def run_prologue():
    print("### PROLOGUE (HARDCODED) ###")
    print("Narrator: Rain taps against the cracked glass of the Old Library as you step inside.")
    print("Mara: Alex. Good. The archive's Echo Shard is missing.")
    print("Alex: Missing? Who had access?")
    print("Mara: A courier team. Eli was last seen near the Market Gate. Start there.")
    print("Mara: Get me the truth.")
    print()

    print("### SCRIPTED CHOICES ###")
    print("How do you answer Mara?")
    print("  1) I'm in. Tell me where to start.")
    print("  2) Why pick me for this?")

    while True:
        c1 = input("Choice > ").strip()
        if c1 in ("1", "2"):
            break
        print("Enter 1 or 2.")

    if c1 == "1":
        print("Alex: I'm in. Tell me where to start.")
        print("Mara is thinking.")
        print("Mara: Good. Keep your head down and your ears open.")
    else:
        print("Alex: Why pick me for this?")
        print("Mara is thinking.")
        print("Mara: Because you don't scare easy, and you still owe me a favor.")

    print("What is your first move?")
    print("  1) Go straight to Eli at the Market Gate.")
    print("  2) Check the library shipping records first.")

    while True:
        c2 = input("Choice > ").strip()
        if c2 in ("1", "2"):
            break
        print("Enter 1 or 2.")

    if c2 == "1":
        final_player_action = "I go to the Market Gate and question Eli about the missing shipment."
        current_npc = "Eli"
        current_location = "Market Gate"
        print("Alex: I'll go to the Market Gate and find Eli.")
        print("Mara is thinking.")
        print("Mara: Ask short questions. Eli lies when people ramble.")
    else:
        final_player_action = "I inspect ledger 7C in the Old Library before meeting Eli."
        current_npc = "Mara"
        current_location = "Old Library"
        print("Alex: I'll check your shipping records first.")
        print("Mara is thinking.")
        print("Mara: Fine. Find ledger 7C, then go to Eli with facts in hand.")

    print("Narrator: The scripted prologue ends. From here, dynamic mode continues.")
    print()

    prologue_summary = (
        "Prologue summary: Mara asked Alex to investigate the missing Echo Shard. "
        "Eli was last seen near the Market Gate. "
        "Player final scripted action: " + final_player_action
    )

    return prologue_summary, final_player_action, current_npc, current_location
