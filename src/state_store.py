"""
src/state_store.py

Canonical world-state storage.
Keeps the game's hard truth plus arc/checkpoint state on disk.
"""

import json
from copy import deepcopy
from pathlib import Path
from src.story_rules import canonicalize_story_state

DEFAULT_KNOWN_LOCATIONS = ["Old Library", "Market Gate"] 
ARC_PLAN = [ #A simple plan for the story arc, helping streer the LLM towards a good storyline. 
    {
        "id": "secure_concrete_lead",
        "phase": "opening",
        "deadline_turn": 3,
        "goal": "Reveal a concrete lead the player can verify immediately.",
    },
    {
        "id": "verify_evidence",
        "phase": "middle",
        "deadline_turn": 6,
        "goal": "Point the player toward evidence, a witness, or a location to inspect.",
    },
    {
        "id": "identify_pressure_point",
        "phase": "middle",
        "deadline_turn": 9,
        "goal": "Surface a suspect, leverage point, threat, debt, or contradiction.",
    },
    {
        "id": "push_resolution",
        "phase": "ending",
        "deadline_turn": 12,
        "goal": "Drive the scene toward confrontation, confession, or reporting the truth.",
    },
]


def build_arc_state(beat_index=0, completed_beats=None):
    completed = list(completed_beats or [])
    if beat_index >= len(ARC_PLAN):
        return {
            "phase": "ending",
            "beat_index": len(ARC_PLAN),
            "next_required_beat": "",
            "next_required_goal": "Resolve the investigation cleanly.",
            "beat_deadline_turn": None,
            "completed_beats": completed,
            "steering_strength": "soft",
        }

    beat = ARC_PLAN[beat_index]
    return {
        "phase": beat["phase"],
        "beat_index": beat_index,
        "next_required_beat": beat["id"],
        "next_required_goal": beat["goal"],
        "beat_deadline_turn": beat["deadline_turn"],
        "completed_beats": completed,
        "steering_strength": "soft",
    }


def advance_arc_state(arc_state):
    current_index = 0
    completed = []
    if isinstance(arc_state, dict):
        current_index = int(arc_state.get("beat_index", 0))
        completed = list(arc_state.get("completed_beats", []))
        current = str(arc_state.get("next_required_beat", "")).strip()
        if current and current not in completed:
            completed.append(current)
    return build_arc_state(current_index + 1, completed_beats=completed)


class WorldStateStore:
    def __init__(self, path="data/state/world_state.json"): #Where the world state is stored on disk
        self.path = Path(path)

    def default_state(
        self,
        prologue_summary,
        first_choice_id,
        first_action_text,
        current_npc,
        current_location,
        handoff_turn_index=2,
    ): #Base state for a new game once prologue hands off to LLM mode
        known_locations = sorted(set(DEFAULT_KNOWN_LOCATIONS + [str(current_location).strip()]))
        return {
            "mode": "llm",
            "generation_enabled": True,
            "current_location": current_location,
            "current_npc": current_npc,
            "time_of_day": "night",
            "day": 1,
            "inventory": [],
            "known_locations": known_locations,
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
            "last_player_action": first_action_text,
            "last_choice_id": first_choice_id,
            "last_choice_text": first_action_text,
            "last_memory_summary": "Investigation has just entered dynamic mode.",
            "handoff_turn_index": handoff_turn_index,
            "turn": 0,
            "arc_state": build_arc_state(),
            "last_narrator": "",
            "last_speaker": "",
            "last_reply": "",
            "last_choices": [],
        }

    def _normalize_choice_list(self, choices):
        normalized = []
        if not isinstance(choices, list):
            return normalized
        for raw_choice in choices:
            if isinstance(raw_choice, dict):
                text = str(raw_choice.get("text", "")).strip()
                choice_id = str(raw_choice.get("id", "")).strip()
                action_type = str(raw_choice.get("action_type", "")).strip() or "ask"
                if text and choice_id:
                    normalized.append(
                        {
                            "id": choice_id,
                            "text": text,
                            "action_type": action_type,
                        }
                    )
            else:
                text = str(raw_choice).strip()
                if text:
                    normalized.append(
                        {
                            "id": text.lower().replace(" ", "_"),
                            "text": text,
                            "action_type": "ask",
                        }
                    )
        return normalized

    def _ensure_defaults(self, state):
        if not isinstance(state, dict):
            return None

        out = deepcopy(state)
        out.setdefault("mode", "llm")
        out.setdefault("generation_enabled", True)
        out.setdefault("current_location", "Market Gate")
        out.setdefault("current_npc", "Eli")
        out.setdefault("time_of_day", "night")
        out.setdefault("day", 1)
        out.setdefault("inventory", [])
        out.setdefault("active_quests", {"echo_shard": "active"})
        out.setdefault(
            "quest_flags",
            {
                "met_eli": False,
                "found_ledger_clue": False,
                "truth_reported": False,
            },
        )
        out.setdefault("npc_relationships", {"Mara": 1, "Eli": 0})
        out.setdefault("prologue_summary", "Prologue summary unavailable.")
        out.setdefault("last_player_action", "I continue the investigation.")
        out.setdefault("last_choice_id", "continue_investigation")
        out.setdefault("last_choice_text", out["last_player_action"])
        out.setdefault("last_memory_summary", "Investigation has just entered dynamic mode.")
        out.setdefault("handoff_turn_index", 2)
        out.setdefault("turn", 0)
        out.setdefault("last_narrator", "")
        out.setdefault("last_speaker", "")
        out.setdefault("last_reply", "")
        out = canonicalize_story_state(out)
        out["last_choices"] = self._normalize_choice_list(out.get("last_choices", []))

        known_locations = out.get("known_locations", [])
        if not isinstance(known_locations, list):
            known_locations = []
        location_values = set(DEFAULT_KNOWN_LOCATIONS)
        for item in known_locations:
            text = str(item).strip()
            if text:
                location_values.add(text)
        current_location = str(out.get("current_location", "")).strip()
        if current_location:
            location_values.add(current_location)
        out["known_locations"] = sorted(location_values)

        arc_state = out.get("arc_state")
        if not isinstance(arc_state, dict):
            out["arc_state"] = build_arc_state()
        else:
            beat_index = int(arc_state.get("beat_index", 0))
            completed = arc_state.get("completed_beats", [])
            if not isinstance(completed, list):
                completed = []
            normalized_arc = build_arc_state(beat_index, completed_beats=completed)
            steering_strength = str(arc_state.get("steering_strength", "soft")).strip().lower()
            if steering_strength not in {"soft", "hard"}:
                steering_strength = "soft"
            normalized_arc["steering_strength"] = steering_strength
            out["arc_state"] = normalized_arc

        return out

    def load(self): #Load the state that we left it in, or make a new one if it doesnt exist or is corrupted
        if not self.path.exists():
            return None
        try:
            raw = self.path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                return self._ensure_defaults(data)
        except Exception:
            return None
        return None

    def save(self, state): #Saving the state to disk
        normalized = self._ensure_defaults(state)
        if normalized is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")

    def reset(self):
        # Remove the saved canonical world state so next launch starts fresh.
        self.path.unlink(missing_ok=True)
