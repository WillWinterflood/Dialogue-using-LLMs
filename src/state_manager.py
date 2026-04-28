'''
src/state_manager.py 

The game state controller 
Essentially keeps track of NPC location and what NPC we are currently on. 
Keeps track of current turn number etc...
'''

import time
from uuid import uuid4 #To give every turn a different id
from src.embedder import embed  # semantic embedding at write time (Problem 1)
from src.memory_retrieval import _build_auto_memory_summary
from src.state_store import advance_arc_state, build_arc_state
from src.story_rules import apply_story_choice, canonicalize_story_state

class StateManager:
    def __init__(self, world_state, state_store, memory_store, current_npc="", current_location="", llm=None):
        self.world_state = canonicalize_story_state(world_state or {})
        self.state_store = state_store
        self.memory_store = memory_store
        self.llm = llm  # Used for LLM importance rating (Problem 3) and reflection
        self.current_npc = self.world_state.get("current_npc", current_npc)
        self.current_location = self.world_state.get("current_location", current_location)
        self.last_rule_effects = {"applied_rules": [], "milestones": []}
        self.pending_story_narration = ""
        try:
            self.turn = max(0, int(self.world_state.get("turn", 0)))
        except Exception:
            self.turn = 0

    def mission_finished(self):
        #Checking whether the case has been closed so the loop knows to stop offering choices
        flags = self.world_state.get("quest_flags", {})
        if not isinstance(flags, dict):
            return False
        return bool(flags.get("case_closed"))

    def _known_npc_map(self):
        known = {}
        relationships = self.world_state.get("npc_relationships", {})
        if isinstance(relationships, dict):
            for npc_name in relationships.keys():
                text = str(npc_name).strip()
                if text:
                    known[text.lower()] = text
        current = str(self.current_npc or "").strip()
        if current:
            known[current.lower()] = current
        return known

    def _known_location_map(self):
        known = {}
        current = str(self.current_location or "").strip()
        if current:
            known[current.lower()] = current

        raw_locations = self.world_state.get("known_locations", [])
        if isinstance(raw_locations, list):
            for location in raw_locations:
                text = str(location).strip()
                if text:
                    known[text.lower()] = text
        return known

    #Have added some planned progression - meaning what checkpoints I want the LLM to hit, this means that this is important to ensure that the LLM doesnt drift off course too much
    def _current_arc_state(self):
        arc_state = self.world_state.get("arc_state")
        if isinstance(arc_state, dict):
            return dict(arc_state)
        return build_arc_state()

    def _apply_inventory_delta(self, add_items=None, remove_items=None):
        #Adding or removing items from inventory, making sure we dont add duplicates
        inventory = self.world_state.get("inventory", [])
        if not isinstance(inventory, list):
            inventory = []

        for item in add_items or []:
            text = str(item).strip()
            if text and text not in inventory:
                inventory.append(text)

        for item in remove_items or []:
            text = str(item).strip()
            if text in inventory:
                inventory.remove(text)

        self.world_state["inventory"] = inventory

    def _advance_arc_for_milestones(self, milestones):
        if not milestones:
            return

        arc_state = self._current_arc_state()
        for milestone in milestones:
            next_beat = str(arc_state.get("next_required_beat", "")).strip()
            if not next_beat:
                break
            if str(milestone).strip() == next_beat:
                arc_state = advance_arc_state(arc_state)
        self.world_state["arc_state"] = arc_state

    def _apply_story_choice_rules(self, player_choice):
        effects = apply_story_choice(self.world_state, player_choice, self.current_npc, self.current_location)
        self.last_rule_effects = effects if isinstance(effects, dict) else {"applied_rules": [], "milestones": []}
        self.pending_story_narration = ""
        if not isinstance(effects, dict):
            return

        current_location = str(effects.get("current_location", "")).strip()
        current_npc = str(effects.get("current_npc", "")).strip()
        if current_location:
            self.current_location = current_location
        if current_npc:
            self.current_npc = current_npc

        for key in ("quest_flags", "active_quests", "npc_relationships"):
            existing = self.world_state.get(key, {})
            if not isinstance(existing, dict):
                existing = {}
            existing.update(effects.get(key, {}))
            self.world_state[key] = existing

        self._apply_inventory_delta(
            add_items=effects.get("inventory_add", []),
            remove_items=effects.get("inventory_remove", []),
        )

        known_locations = self.world_state.get("known_locations", [])
        if not isinstance(known_locations, list):
            known_locations = []
        for location in effects.get("known_locations", []):
            text = str(location).strip()
            if text:
                known_locations.append(text)
        if self.current_location:
            known_locations.append(self.current_location)
        self.world_state["known_locations"] = sorted(
            {str(item).strip() for item in known_locations if str(item).strip()}
        )

        self.world_state["current_location"] = self.current_location
        self.world_state["current_npc"] = self.current_npc
        self.world_state = canonicalize_story_state(self.world_state)
        self._advance_arc_for_milestones(effects.get("milestones", []))

        narrator_lines = effects.get("narrator_lines", [])
        if isinstance(narrator_lines, list):
            text = " ".join(str(line).strip() for line in narrator_lines if str(line).strip())
            if text:
                self.pending_story_narration = text

    def _apply_arc_update(self, parsed_output):
        #If we are approaching the deadline turn for the current beat, switch to hard steering so the LLM is more forcefully guided
        arc_state = self._current_arc_state()
        deadline_turn = arc_state.get("beat_deadline_turn")
        arc_state["steering_strength"] = "soft"
        if deadline_turn is not None and self.turn + 1 >= int(deadline_turn):
            arc_state["steering_strength"] = "hard"
        self.world_state["arc_state"] = arc_state

    def _apply_state_updates(self, player_choice, parsed_output):
        updates = parsed_output.get("state_updates")
        if not isinstance(updates, dict):
            updates = {}

        new_time = updates.get("time_of_day")
        if isinstance(new_time, str) and new_time.strip():
            self.world_state["time_of_day"] = new_time.strip()

        new_day = updates.get("day")
        if isinstance(new_day, int) and new_day > 0:
            self.world_state["day"] = new_day

        known_locations = self.world_state.get("known_locations", [])
        if not isinstance(known_locations, list):
            known_locations = []
        if self.current_location and self.current_location not in known_locations:
            known_locations.append(self.current_location)
        self.world_state["known_locations"] = sorted({str(item).strip() for item in known_locations if str(item).strip()})

        self._apply_arc_update(parsed_output)
        self.world_state["mode"] = "llm"
        self.world_state["generation_enabled"] = True
        self.world_state["current_location"] = self.current_location
        self.world_state["current_npc"] = self.current_npc
        self.world_state["last_player_action"] = player_choice.get("text", "")
        self.world_state["last_choice_id"] = player_choice.get("id", "")
        self.world_state["last_choice_text"] = player_choice.get("text", "")
        self.world_state["last_memory_summary"] = parsed_output.get("memory_summary", "")
        self.world_state["turn"] = self.turn
        self.world_state = canonicalize_story_state(self.world_state)

    def _apply_pending_story_narration(self, parsed_output):
        if not isinstance(parsed_output, dict):
            return parsed_output

        bridge = str(self.pending_story_narration or "").strip()
        narrator = str(parsed_output.get("narrator", "")).strip()
        if bridge:
            if narrator and bridge.lower() not in narrator.lower():
                parsed_output["narrator"] = f"{bridge} {narrator}".strip()
            elif not narrator:
                parsed_output["narrator"] = bridge

        self.pending_story_narration = ""
        return parsed_output

    def _rate_importance_with_llm(self, memory_summary):
        """Ask the LLM to score this memory's importance from 1-10.

        Generative Agents (Park et al. 2023) uses LLM-rated importance as one
        of three retrieval signals alongside recency and relevance.  A direct
        rating is richer than the heuristic in output_validator.py which only
        checks event_type and whether state/arc updates are non-empty.
        Returns None on any failure so the caller falls back to the validator estimate.
        """
        if not self.llm:
            return None
        try:
            prompt = (
                "Rate the importance of this investigation memory on a scale of 1 to 10. "
                "1 = trivial small talk, 10 = critical evidence or plot turning point. "
                "Reply with only a single integer.\n\n"
                f"Memory: {memory_summary}"
            )
            raw = self.llm.generate([{"role": "user", "content": prompt}])
            # Parse the first integer token in the valid range
            for token in str(raw).split():
                cleaned = token.strip(".,!?\"'")
                try:
                    val = int(cleaned)
                    if 1 <= val <= 10:
                        return val
                except ValueError:
                    continue
        except Exception:
            pass
        return None

    def _maybe_reflect(self, current_npc, turn, every_n=5):
        """Every every_n turns, compress recent NPC memories into a single reflection event.

        Without compression the JSONL files grow unboundedly and the MEMORY_TOP_K cap
        (currently 2) means most individual turns are never retrieved at all.  A single
        reflection captures the gist of several turns in fewer tokens, giving the
        retriever a denser, higher-importance candidate to surface.

        This mirrors the 'reflection' step in Generative Agents (Park et al. 2023)
        where the agent periodically synthesises lower-level observations into
        higher-level insights that persist longer than any individual memory.
        """
        if not self.llm or turn % every_n != 0:
            return
        recent = self.memory_store.load_npc_turns(current_npc, n=every_n)
        # Skip events that are themselves reflections to avoid compressing compressions
        summaries = [
            e.get("memory_summary", "").strip()
            for e in recent
            if e.get("memory_summary", "").strip() and e.get("event_type") != "reflection"
        ]
        if len(summaries) < 3:
            return
        try:
            prompt = (
                f"Summarise what Alex has learned about {current_npc} from these observations "
                f"in 1-2 sentences. Be specific and factual. Reply with only the summary.\n\n"
                + "\n".join(f"- {s}" for s in summaries)
            )
            reflection = self.llm.generate([{"role": "user", "content": prompt}]).strip()
            if not reflection:
                return
            emb = embed(reflection)
            self.memory_store.append_npc_memory(current_npc, {
                "event_id": f"reflection_{current_npc}_{turn}_{uuid4().hex[:6]}",
                "timestamp": time.time(),
                "turn": turn,
                "mode": "reflection",
                "event_type": "reflection",
                "memory_summary": reflection,
                "importance": 7,  # High — reflections are durable synthesised facts
                "embedding": emb.tolist() if emb is not None else None,
                "current_npc": current_npc,
                "current_location": self.current_location,
                "tags": ["reflection", current_npc.lower()],
                "quest_ids": sorted(self.world_state.get("active_quests", {}).keys()),
            })
        except Exception:
            pass

    def _persist_turn_memory(self, player_choice, parsed_output, retrieval_meta):
        self.world_state["last_narrator"] = parsed_output["narrator"]
        self.world_state["last_speaker"] = parsed_output["speaker"]
        self.world_state["last_reply"] = parsed_output["reply"]
        self.world_state["last_choices"] = list(parsed_output["choices"])
        #Keeping track of which NPCs Alex has spoken to, used in the prompt to decide if this is a first conversation
        spoken_npcs = self.world_state.get("spoken_npcs", [])
        if not isinstance(spoken_npcs, list):
            spoken_npcs = []
        speaker = str(parsed_output.get("speaker", "")).strip()
        if speaker and speaker.lower() not in {str(name).strip().lower() for name in spoken_npcs}:
            spoken_npcs.append(speaker)
        self.world_state["spoken_npcs"] = spoken_npcs
        self.state_store.save(self.world_state)

        memory_summary = parsed_output.get("memory_summary", "")
        if not isinstance(memory_summary, str) or not memory_summary.strip():
            memory_summary = _build_auto_memory_summary(
                parsed_output.get("speaker", ""),
                parsed_output.get("reply", ""),
                current_npc=self.current_npc,
                current_location=self.current_location,
            )

        # Embed the memory summary for semantic retrieval (Problem 1).
        # Stored as a plain Python list so it serialises cleanly to JSONL.
        # Returns None if sentence-transformers is not installed — the scorer
        # in memory_retrieval.py falls back to keyword overlap in that case.
        summary_embedding = embed(memory_summary)
        embedding_list = summary_embedding.tolist() if summary_embedding is not None else None

        # LLM-rated importance (Problem 3 — Generative Agents style).
        # Asking the model directly is richer than the heuristic estimate in
        # output_validator.py which only checks event_type and state/arc updates.
        # Falls back to the validator estimate on any failure.
        llm_importance = self._rate_importance_with_llm(memory_summary)
        importance = llm_importance if llm_importance is not None else parsed_output.get("importance", 3)

        event = {
            "event_id": f"turn_{self.turn}_{uuid4().hex[:8]}",
            "timestamp": time.time(),
            "turn": self.turn,
            "mode": "llm",
            "choice_id": player_choice.get("id"),
            "choice_text": player_choice.get("text"),
            "action_type": player_choice.get("action_type"),
            "narrator": parsed_output["narrator"],
            "speaker": parsed_output["speaker"],
            "reply": parsed_output["reply"],
            "choices": parsed_output["choices"],
            "current_npc": self.current_npc,
            "current_location": self.current_location,
            "memory_summary": memory_summary,
            "state_updates": parsed_output.get("state_updates", {}),
            "arc_update": parsed_output.get("arc_update", {}),
            "event_type": parsed_output.get("event_type", "dialogue"),
            "tags": parsed_output.get("tags", []),
            "importance": importance,
            "embedding": embedding_list,
            "quest_ids": sorted(self.world_state.get("active_quests", {}).keys()),
            "retrieved_memory_ids": [item.get("event_id") for item in retrieval_meta.get("selected", [])],
            "retrieval_scores": [
                {
                    "event_id": item.get("event_id"),
                    "score": round(float(item.get("score", 0.0)), 4),
                }
                for item in retrieval_meta.get("selected", [])
            ],
            "rule_effects": self.last_rule_effects,
        }
        self.memory_store.append_turn(event)
        self.memory_store.append_npc_memory(parsed_output.get("speaker"), event)

        # Every 5 turns, compress recent NPC memories into a single reflection.
        # Prevents retrieval noise from accumulating as the session grows.
        self._maybe_reflect(self.current_npc, self.turn)
