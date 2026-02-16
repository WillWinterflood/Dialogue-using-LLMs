'''
src/story_data.py

This builds the initial world state, defining the player and NPC profiles, starting quest and the prologue
'''

from story_game.models import Character, DialogueEntry, GameState, NPC, Quest

def build_initial_state():
    #Creating the character
    player = Character(
        name="Alex",
        role="Main Character",
        bio="A young systems apprentice who returned to town after a long absence.",
        traits=["curious", "persistent", "morally conflicted"],
        speaking_style="Direct questions, reflective under pressure.",
    )
    #creating some NPCs to start with
    npcs = {
        "mara": NPC(
            name="Mara",
            role="Town Archivist",
            bio="Protective of old knowledge, sharp but fair.",
            traits=["controlled", "intense", "duty-driven"],
            speaking_style="Short, precise, no-nonsense.",
            location="Old Library",
            trust_level=1,
        ),
        "eli": NPC(
            name="Eli",
            role="Courier",
            bio="Fast-talking messenger who hears everything first.",
            traits=["street-smart", "evasive", "opportunistic"],
            speaking_style="Quick, slippery, tests people before revealing facts.",
            location="Market Gate",
            trust_level=0,
        ),
    }

    quests = {
        "echo_shard": Quest(
            quest_id="echo_shard",
            title="The Missing Echo Shard",
            description="Find the shard that powers the archive records.",
            giver="Mara",
            status="active",
            objective="Ask Eli at the Market Gate where the shard shipment went.",
        )
    }

    state = GameState(
        player=player,
        npcs=npcs,
        quests=quests,
        active_npc="mara",
        story_act="beginning",
        story_goal="Recover the missing Echo Shard and decide what truth to report.",
    )

    for line in scripted_intro():
        state.history.append(line)
    
    state.phase = "dynamic"
    return state

def scripted_intro():
    return [
        DialogueEntry(
            speaker="Narrator",
            text="Rain taps against the cracked glass of the Old Library as you step inside.",
            mode="scripted",
            tags=["scene_start"],
        ),
        DialogueEntry(
            speaker="Mara",
            text="Alex. Good. The archive's Echo Shard is missing.",
            mode="scripted",
            tags=["quest_hook"],
        ),
        DialogueEntry(
            speaker="Alex",
            text="Missing? Who had access?",
            mode="scripted",
        ),
        DialogueEntry(
            speaker="Mara",
            text="A courier team. Eli was last seen near the Market Gate. Start there.",
            mode="scripted",
            tags=["quest_assigned"],
        ),
        DialogueEntry(
            speaker="Mara",
            text="Get me the truth.",
            mode="scripted",
            tags=["tone_set"],
        ),
    ]
