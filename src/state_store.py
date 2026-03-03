"""
src/state_store.py

Simple world-state storage
This file keeps one canonical snapshot of the game's truth on disk
"""

import json
from pathlib import Path

class WorldStateStore:
    def __init__(self, path="data/state/world_state.json"): #Where the world state is stored on disk
        self.path = Path(path)

    def default_state(self, prologue_summary, first_action, current_npc, current_location): #Base state for a new game
        return {
            "current_location": current_location,
            "current_npc": current_npc,
            "time_of_day": "night",
            "day": 1,
            "inventory": [],
            "active_quests": {"echo_shard": "active"},
            "quest_flags": {
                "met_eli": False,
                "found_ledger_clue": False,
                "truth_reported": False,
            },
            "npc_relationships": {
                "Mara": 1,
                "Eli": 0,
            },
            "prologue_summary": prologue_summary,
            "last_player_action": first_action,
            "last_memory_summary": "Investigation has just entered dynamic mode.",
            "turn": 0,
        }

    def load(self): #Load the state that we left it in, or make a new one if it doesnt exist or is corrupted
        if not self.path.exists():
            return None
        try:
            raw = self.path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except Exception:
            return None
        return None

    def save(self, state): #Saving the state to disk
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def reset(self):
        # Remove the saved canonical world state so next launch starts fresh.
        self.path.unlink(missing_ok=True)
