'''
game.py

Commit 5c runtime:
- Takes a snapshot of the current world state 
- And then saves this as a checkpoint
'''

import json
from pathlib import Path 

from src.choice_loop import ChoiceLoop
from src.llm_runtime import LocalLLM
from src.prologue import run_prologue
from src.memory_store import MemoryStore
from src.state_store import WorldStateStore

LOG_PATH = Path("dialogue_log.jsonl")

def _choose_saved_state_action(): #Asking user whether they want to continue from the last saved or reset
    print("Saved world state found.")
    print("  1) Continue previous session")
    print("  2) Restart game and reset history/logs")

    while True:
        raw = input("Choice > ").strip()
        if raw in {"1", "2"}:
            return raw
        print("Enter 1 or 2.")

def _append_scripted_log(event, index):
    row = {
        "mode": "scripted",
        "scripted_index": index,
        "scene_id": event.get("scene_id"),
        "choice_id": event.get("choice_id"),
        "choice_text": event.get("choice_text"),
        "memory_summary": event.get("memory_summary"),
        "event_type": event.get("event_type"),
        "importance": event.get("importance"),
        "tags": event.get("tags", []),
        "quest_ids": event.get("quest_ids", []),
        "current_npc": event.get("current_npc"),
        "current_location": event.get("current_location"),
    }
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")

def _reset_runtime_data(state_store, memory_store):
    state_store.reset()
    memory_store.reset()
    LOG_PATH.unlink(missing_ok=True)

def _start_new_game(state_store, memory_store):
    print("Choice loop ready. /quit or /exit to stop.")
    prologue_summary, handoff = run_prologue()
    world_state = state_store.default_state(
        prologue_summary,
        handoff["first_choice_id"],
        handoff["first_action_text"],
        handoff["current_npc"],
        handoff["current_location"],
        handoff_turn_index=handoff["handoff_turn_index"],
    )
    state_store.save(world_state)

    for index, event in enumerate(handoff["scripted_events"], start=1):
        scripted_event = dict(event)
        scripted_event.setdefault("event_id", f"scripted_{index}")
        scripted_event.setdefault("turn", 0)
        memory_store.append_turn(scripted_event)
        memory_store.append_npc_memory(scripted_event.get("current_npc"), scripted_event)
        _append_scripted_log(scripted_event, index)

    initial_player_choice = {
        "id": handoff["first_choice_id"],
        "text": handoff["first_action_text"],
        "action_type": handoff["first_action_type"],
    }
    return prologue_summary, initial_player_choice, world_state, False

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
            initial_player_choice = {
                "id": saved_state.get("last_choice_id", "continue_investigation"),
                "text": saved_state.get("last_choice_text", saved_state.get("last_player_action", "I continue the investigation.")),
                "action_type": "resume",
            }
            current_npc = saved_state.get("current_npc", "Eli")
            current_location = saved_state.get("current_location", "Market Gate")
            world_state = saved_state
            resume_mode = True
        else:
            print("Restarting game and clearing history/logs.")
            _reset_runtime_data(state_store, memory_store)
            prologue_summary, initial_player_choice, world_state, resume_mode = _start_new_game(state_store, memory_store)
            current_npc = world_state.get("current_npc", "Eli")
            current_location = world_state.get("current_location", "Market Gate")
    else:
        prologue_summary, initial_player_choice, world_state, resume_mode = _start_new_game(state_store, memory_store)
        current_npc = world_state.get("current_npc", "Eli")
        current_location = world_state.get("current_location", "Market Gate")

    loop = ChoiceLoop(
        llm=llm,
        prologue_summary=prologue_summary,
        initial_player_choice=initial_player_choice,
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
