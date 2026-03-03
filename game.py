'''
game.py

Commit 5b runtime:
- Takes a snapshot of the current world state 
- And then saves this as a checkpoint
'''

from src.choice_loop import ChoiceLoop
from src.llm_runtime import LocalLLM
from src.prologue import run_prologue
from src.memory_store import MemoryStore
from src.state_store import WorldStateStore

def _choose_saved_state_action(): #Asking user whether they want to continue from the last saved or reset
    print("Saved world state found.")
    print("  1) Continue previous session")
    print("  2) Reset save and restart story")

    while True:
        raw = input("Choice > ").strip()
        if raw in {"1", "2"}:
            return raw
        print("Enter 1 or 2.")


def main():
    llm = LocalLLM()
    try:
        llm.load()
    except Exception as exc:
        print(f"Startup error: {exc}")
        return

    state_store = WorldStateStore()
    memory_store = MemoryStore()

    saved_state = state_store.load() #Continue from the last saved state if it exists
    if saved_state:
        choice = _choose_saved_state_action()
        if choice == "1":
            print("Continuing previous session.")
            prologue_summary = saved_state.get("prologue_summary", "Prologue summary unavailable.")
            final_player_action = saved_state.get("last_player_action", "I continue the investigation.")
            current_npc = saved_state.get("current_npc", "Eli")
            current_location = saved_state.get("current_location", "Market Gate")
            world_state = saved_state
            resume_mode = True
        else:
            print("Resetting save data and restarting from prologue.")
            state_store.reset()
            memory_store.reset()
            print("Choice loop ready. /quit or /exit to stop.")
            prologue_summary, final_player_action, current_npc, current_location = run_prologue()
            world_state = state_store.default_state(
                prologue_summary,
                final_player_action,
                current_npc,
                current_location,
            )
            state_store.save(world_state)
            resume_mode = False
    else:
        print("Choice loop ready. /quit or /exit to stop.")
        prologue_summary, final_player_action, current_npc, current_location = run_prologue()
        world_state = state_store.default_state(
            prologue_summary,
            final_player_action,
            current_npc,
            current_location,
        )
        state_store.save(world_state)
        resume_mode = False

    loop = ChoiceLoop(
        llm=llm,
        prologue_summary=prologue_summary,
        initial_player_action=final_player_action,
        current_npc=current_npc,
        current_location=current_location,
        world_state=world_state,
        state_store=state_store,
        memory_store=memory_store,
        resume_mode=resume_mode,
    )
    loop.run()


if __name__ == "__main__":
    main()
