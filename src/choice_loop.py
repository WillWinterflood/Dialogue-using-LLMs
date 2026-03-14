'''
src/choice_loop.py

Choice-driven dynamic loop:
- build constrained prompt
- generate JSON
- validate minimal schema
- log each turn
- print NPC dialogue and next choices

This file is to do with the dialogue loop, where the player is given the choices and the NPC dialogue is generated y the LLM
The LLM is expected to handle everything from state updates, quest updates, inventory changes etc... 
This is to make it so it can actually be used as a game.
'''

import json
import re
import time
from pathlib import Path
from uuid import uuid4

from src.state_store import advance_arc_state, build_arc_state
from src.story_rules import apply_story_choice, canonicalize_story_state, suggest_story_choices
from src.text_fx import type_line #Typewriter thing as it makes it look better

PROMPT_PATH = Path("prompts/prompt_v1.txt")
LOG_PATH = Path("dialogue_log.jsonl")
POST_RESPONSE_PAUSE_SECONDS = 0.2 #small pause to allow for reading
PLAYER_CHOICE_SPEAK_SECONDS = 0.2
MAX_JSON_RETRY_ATTEMPTS = 2
MIN_LLM_CHOICES = 2
MAX_LLM_CHOICES = 3
MEMORY_RECENT_TURNS = 8  #How many global turns to load for retrieval
MEMORY_NPC_TURNS = 20 #How many NPC-specific turns to load for retrieval
MEMORY_TOP_K = 4#how many memory summaries to inject into the prompt
MEMORY_TOKEN_BUDGET = 220 #Max tokens to spend on memory summaries, in order to not fill the prompt with too much memory

#Changed some of these to be good for a game, whereas before it was more for LLM capabilities, forexample there is so many more action types that are relevant
 
VALID_TIME_OF_DAY = {"dawn", "morning", "noon", "afternoon", "evening", "night"}
ALLOWED_QUEST_STATUS = {"not_started", "active", "completed", "failed"}
ALLOWED_ACTION_TYPES = {"ask", "investigate", "travel", "accuse", "reassure", "threaten", "trade", "exit", "resume"}
ALLOWED_EVENT_TYPES = {"dialogue", "clue", "promise", "debt", "threat", "travel", "quest", "fallback", "handoff", "prologue"}
ALLOWED_STATE_UPDATE_KEYS = {
    "time_of_day",
    "day",
}
GENERIC_LOOP_MARKERS = ( #Usually when coming to the end of a conversation, the LLM has started to repeat itself and give the same choices 
    # These added should help break out of loops.
    "anything else",
    "suspicious activity",
    "what else",
    "tell me more",
)
STOPWORDS = { #Words that are very common and therefor not needed for the prompt as they dont add much value 
    "the",
    "and",
    "that",
    "with",
    "from",
    "this",
    "what",
    "where",
    "when",
    "your",
    "have",
    "into",
    "about",
    "there",
    "their",
    "them",
    "then",
    "just",
    "give",
    "tell",
    "right",
    "they",
    "will",
    "would",
    "could",
    "should",
    "need",
    "asks",
    "alex",
}

class ChoiceLoop:
    def __init__(
        self,
        llm,
        prologue_summary,
        initial_player_choice,
        current_npc,
        current_location,
        world_state,
        state_store,
        memory_store,
        resume_mode=False,
    ):
        self.llm = llm
        self.prologue_summary = prologue_summary
        self.initial_player_choice = dict(initial_player_choice or {})
        self.world_state = canonicalize_story_state(world_state or {})
        self.state_store = state_store
        self.memory_store = memory_store
        self.resume_mode = resume_mode
        self.current_npc = self.world_state.get("current_npc", current_npc)
        self.current_location = self.world_state.get("current_location", current_location)
        self.last_memory_summary = "Investigation has just entered dynamic mode."
        if self.world_state.get("last_memory_summary"): #Memory summary to then be used in prompt
            self.last_memory_summary = self.world_state["last_memory_summary"] #Giving the LLM context
        self.prompt_template = self._load_prompt_template()
        self.messages = [
            {
                "role": "system",
                "content": "You are a grounded fantasy NPC narrator. Keep replies short and specific.",
            }
        ]
        saved_turn = self.world_state.get("turn", 0) #Resuming from the last turn if you want to carry on
        try:
            self.turn = max(0, int(saved_turn)) 
        except Exception:
            self.turn = 0 
        self.last_choices = self._coerce_choice_list(self.world_state.get("last_choices", []))
        self.max_history_messages = 8
        self.current_player_choice = {} #Tracking the latest choice object
        self.last_retrieval = {
            "query": {},
            "selected": [],
            "candidate_count": 0,
            "memory_tokens": 0,
            "prompt_tokens": 0,
        }
        self.last_rule_effects = {"applied_rules": [], "milestones": []}

    def _safe_input(self, label):
        try:
            return input(label).strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSession ended.")
            return None

    def _safe_token_count(self, text): #W
        try:
            return self.llm.count_tokens_text(text)
        except Exception:
            return max(1, len(str(text or "").split()))

    def _slugify(self, text):
        value = re.sub(r"[^a-z0-9]+", "_", str(text or "").strip().lower())
        value = re.sub(r"_+", "_", value).strip("_")
        return value

    def _normalise_choice_text(self, raw_text): #Cleaning up the LLM output
        text = str(raw_text or "").strip()
        if not text:
            return ""
        if text.startswith('"') and text.endswith('"') and len(text) >= 2:
            text = text[1:-1].strip()
        if not text:
            return ""

        text = " ".join(text.split())
        low = text.lower()
        malformed = ("i tell ", "i show ", "i give ", "i ask ", "i check ", "i look ", "i search ", "i explain ")
        if low.startswith(malformed):
            parts = text.split(maxsplit=2)
            if len(parts) >= 2:
                verb = parts[1].capitalize()
                rest = parts[2] if len(parts) >= 3 else ""
                text = f"{verb} {rest}".strip()

        if text and text[-1] not in ".!?":
            text += "."
        return text

    def _normalise_choice(self, raw_choice, fallback_index=0): #
        if isinstance(raw_choice, dict):
            text = raw_choice.get("text") or raw_choice.get("label") or raw_choice.get("utterance")
            choice_id = raw_choice.get("id")
            action_type = str(raw_choice.get("action_type", "ask")).strip().lower() or "ask"
        else:
            text = raw_choice
            choice_id = ""
            action_type = "ask"

        clean_text = self._normalise_choice_text(text)
        if not clean_text:
            return None

        clean_id = self._slugify(choice_id or clean_text)
        if not clean_id:
            clean_id = f"choice_{fallback_index or 1}"
        if action_type not in ALLOWED_ACTION_TYPES:
            action_type = "ask"
        return {"id": clean_id, "text": clean_text, "action_type": action_type}

    def _coerce_choice_list(self, raw_choices): #Cleaning the list of choices for the LLM
        cleaned = []
        for idx, raw_choice in enumerate(raw_choices or [], start=1):
            choice = self._normalise_choice(raw_choice, fallback_index=idx)
            if choice:
                cleaned.append(choice)
        return cleaned

    def _choice_key(self, choice):
        if isinstance(choice, dict):
            return str(choice.get("id", "")).strip().lower()
        return self._slugify(choice)

    def _choice_text(self, choice):
        if isinstance(choice, dict):
            return str(choice.get("text", "")).strip()
        return self._normalise_choice_text(choice)

    def _is_generic_loop_choice(self, choice): #seeing whether its a generic choice, stuck in a loop
        low = self._choice_text(choice).lower()
        return any(marker in low for marker in GENERIC_LOOP_MARKERS)

    def _build_progress_choice(self, blocked_keys): #Building a choice that should progress the story
        npc = str(self.current_npc or "").strip()
        location = str(self.current_location or "").strip()
        candidates = [
            {"text": "Give me one concrete lead I can verify right now.", "action_type": "ask"},
            {"text": "Who can confirm your version of events?", "action_type": "ask"},
            {"text": "What evidence can I check right now?", "action_type": "investigate"},
            {"text": "Where exactly should I investigate next?", "action_type": "travel"},
        ]
        if location:
            candidates.insert(1, {"text": f"Where in {location} should I investigate next?", "action_type": "travel"})
        if npc:
            candidates.insert(2, {"text": f"{npc}, name one person I should question next.", "action_type": "ask"})

        for idx, candidate in enumerate(candidates, start=1):
            choice = self._normalise_choice(
                {
                    "id": self._slugify(candidate["text"]),
                    "text": candidate["text"],
                    "action_type": candidate["action_type"],
                },
                fallback_index=idx,
            )
            key = self._choice_key(choice)
            if key and key not in blocked_keys:
                return choice
        return {
            "id": "ask_for_concrete_lead",
            "text": "Give me one concrete lead I can verify right now.",
            "action_type": "ask",
        }

    def _enforce_progress_choice(self, cleaned_choices): #If the LLm is repeating we want to force it to give something that will progress it
        if not cleaned_choices:
            return cleaned_choices

        previous_keys = {self._choice_key(c) for c in self.last_choices if self._choice_key(c)}
        current_keys = [self._choice_key(c) for c in cleaned_choices]
        repeated_count = sum(1 for key in current_keys if key in previous_keys)
        all_generic = all(self._is_generic_loop_choice(c) for c in cleaned_choices)
        looping = bool(previous_keys) and (repeated_count == len(cleaned_choices) or (repeated_count >= 1 and all_generic))

        if not looping:
            return cleaned_choices 

        progress = self._build_progress_choice(set(current_keys) | previous_keys)
        if len(cleaned_choices) == 1:
            return [cleaned_choices[0], progress]
        cleaned_choices[-1] = progress
        return cleaned_choices

    def _inject_story_choice(self, cleaned_choices): #injecting some suggestions for LLM 
        suggestions = suggest_story_choices(self.world_state, self.current_npc, self.current_location) 
        if not suggestions:
            return cleaned_choices

        existing_keys = {self._choice_key(choice) for choice in cleaned_choices if self._choice_key(choice)}
        previous_keys = {self._choice_key(choice) for choice in self.last_choices if self._choice_key(choice)}  
  
        for suggestion in suggestions: 
            choice = self._normalise_choice(suggestion, fallback_index=len(cleaned_choices) + 1)
            if not choice: 
                continue
            key = self._choice_key(choice)
            if not key or key in existing_keys:
                continue
 
            if len(cleaned_choices) < MAX_LLM_CHOICES:
                cleaned_choices.append(choice)
                return cleaned_choices
 
            replace_index = None
            for idx in range(len(cleaned_choices) - 1, -1, -1):
                candidate = cleaned_choices[idx]
                candidate_key = self._choice_key(candidate)
                if self._is_generic_loop_choice(candidate) or candidate_key in previous_keys:
                    replace_index = idx
                    break
            if replace_index is None:
                replace_index = len(cleaned_choices) - 1
            cleaned_choices[replace_index] = choice
            return cleaned_choices 
        return cleaned_choices

    def _apply_inventory_delta(self, add_items=None, remove_items=None): 
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
        for _ in milestones:
            next_beat = str(arc_state.get("next_required_beat", "")).strip()
            if not next_beat:
                break
            arc_state = advance_arc_state(arc_state)
        self.world_state["arc_state"] = arc_state

    def _apply_story_choice_rules(self, player_choice): #
        effects = apply_story_choice(self.world_state, player_choice, self.current_npc, self.current_location)
        self.last_rule_effects = effects
        if not isinstance(effects, dict):
            self.last_rule_effects = {"applied_rules": [], "milestones": []}
            return

        current_location = str(effects.get("current_location", "")).strip()
        current_npc = str(effects.get("current_npc", "")).strip()
        if current_location:
            self.current_location = current_location
        if current_npc:
            self.current_npc = current_npc

        flags = self.world_state.get("quest_flags", {})
        if not isinstance(flags, dict):
            flags = {}
        flags.update(effects.get("quest_flags", {}))
        self.world_state["quest_flags"] = flags

        active_quests = self.world_state.get("active_quests", {})
        if not isinstance(active_quests, dict):
            active_quests = {}
        active_quests.update(effects.get("active_quests", {}))
        self.world_state["active_quests"] = active_quests

        relationships = self.world_state.get("npc_relationships", {})
        if not isinstance(relationships, dict):
            relationships = {}
        relationships.update(effects.get("npc_relationships", {}))
        self.world_state["npc_relationships"] = relationships

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

    def _prompt_for_choice(self):
        while True:
            raw = self._safe_input("Choice > ")
            if raw is None:
                return None
            if raw.lower() in {"/quit", "/exit"}:
                print("Session ended.")
                return None
            if not raw.isdigit():
                print("Please choose by number.")
                continue
            selected = self._select_choice_from_number(raw)
            if selected:
                return selected
            print("Invalid choice number. Try again.")

    def _select_choice_from_number(self, raw_text):
        text = str(raw_text or "").strip()
        if not text.isdigit() or not self.last_choices:
            return None
        idx = int(text)
        if not (1 <= idx <= len(self.last_choices)):
            return None

        selected = dict(self.last_choices[idx - 1])
        print("Alex is thinking...")
        if PLAYER_CHOICE_SPEAK_SECONDS > 0:
            time.sleep(PLAYER_CHOICE_SPEAK_SECONDS)
        type_line(f"Alex: {selected['text']}")
        return selected

    def _thinking_label(self): #Label to show someonen is thinking, makes it more immersive
        name = str(self.current_npc).strip() or "Someone"
        return f"{name} is thinking..."

    def _load_prompt_template(self): #loading the prompt template from a file
        if not PROMPT_PATH.exists():
            raise RuntimeError(f"Prompt file not found: {PROMPT_PATH}")
        return PROMPT_PATH.read_text(encoding="utf-8").strip()

    def _extract_json_object(self, raw_text): #Now extracting the Json from the LLM output
        text = str(raw_text or "").strip()
        if not text:
            return None
        try: #We parse the whole thing first, hwoever this is unlikely that the LLM will output perfectly
            return json.loads(text)
        except Exception:
            pass

        start = text.find("{") #Failing that, we find the first json object and parse that
        if start == -1:
            return None

        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}": #Finding the end of the json object
                depth -= 1
                if depth == 0:
                    chunk = text[start : i + 1]
                    try:
                        return json.loads(chunk)
                    except Exception:
                        return None
        return None

    def _build_auto_memory_summary(self, speaker_text, reply_text):
        # Keep this short and deterministic so retrieval has something useful
        # even when the model forgets memory_summary.
        speaker = speaker_text.strip() or str(self.current_npc or "NPC").strip() or "NPC"
        location = str(self.current_location or "current location").strip()
        reply_clean = " ".join(str(reply_text or "").strip().split())
        if reply_clean:
            if len(reply_clean) > 120:
                reply_clean = reply_clean[:117].rstrip() + "..."
            return f"{speaker} replied at {location}: {reply_clean}"
        return f"{speaker} spoke with Alex at {location}."

    def _known_npc_map(self): #Building a map on known npcs
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

    def _known_location_map(self): #Building a map on locations
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

    def _current_arc_state(self):
        arc_state = self.world_state.get("arc_state")
        if isinstance(arc_state, dict):
            return dict(arc_state)
        return build_arc_state()

    def _sanitize_state_updates(self, updates): 
        if not isinstance(updates, dict):
            return {}, []

        cleaned = {} #Cleaned version to the LLM to make sure that the LLM doesnt mess up
        errors = []

        if "time_of_day" in updates: #
            value = str(updates.get("time_of_day", "")).strip().lower()
            if value in VALID_TIME_OF_DAY:
                cleaned["time_of_day"] = value

        if "day" in updates: 
            day = updates.get("day")
            if isinstance(day, int) and not isinstance(day, bool) and day > 0:
                cleaned["day"] = day

        return cleaned, errors

    def _sanitize_arc_update(self, raw_arc_update):
        cleaned = {"advance": False, "beat_id": "", "reason": ""}
        if raw_arc_update is None:
            raw_arc_update = {}
        if not isinstance(raw_arc_update, dict):
            return cleaned, []

        cleaned["reason"] = " ".join(str(raw_arc_update.get("reason", "")).strip().split())[:160]
        return cleaned, []

    def _tokenize_for_match(self, text):
        tokens = set()
        for token in re.findall(r"[a-z0-9_]+", str(text or "").lower()):
            if len(token) < 3 or token in STOPWORDS:
                continue
            tokens.add(token)
        return tokens

    def _derive_tags(self, reply_text, memory_summary):
        tags = []
        seen = set()

        def add_tag(value):
            tag = self._slugify(value)
            if tag and tag not in seen:
                seen.add(tag)
                tags.append(tag)

        add_tag(self.current_npc)
        add_tag(self.current_location)
        for quest_id in sorted(self.world_state.get("active_quests", {}).keys()):
            add_tag(quest_id)
        for term in sorted(self._tokenize_for_match(f"{reply_text} {memory_summary}")):
            add_tag(term)
            if len(tags) >= 6:
                break
        return tags[:6]

    def _estimate_importance(self, event_type, state_updates, arc_update):#Estimating the importance of the even, this is good for knowing how important 
        # the event is, meaning more important events can be prioritised in memory retrieval.
        score = 3
        if state_updates:
            score += 2
        if arc_update.get("advance"):
            score += 2
        if event_type in {"clue", "threat", "quest"}:
            score += 1
        return max(0, min(10, score))

    def _validate_output(self, parsed): #Ensure it has the correct types
        if not isinstance(parsed, dict):
            return False, None, ["Output is not a JSON object."]

        errors = []
        narrator_text = parsed.get("narrator", "")
        if not isinstance(narrator_text, str):
            errors.append("Key 'narrator' must be str")
            narrator_text = ""
        narrator_text = narrator_text.strip()

        speaker_text = str(parsed.get("speaker", "")).strip()
        reply_text = str(parsed.get("reply", "")).strip()
        active_npc = str(self.current_npc or "").strip()
        current_choice_text = str(self.current_player_choice.get("text", "")).strip().lower()

        if not speaker_text or not reply_text:
            errors.append("Dialogue mode: speaker and reply must both be non-empty.")
        if active_npc and speaker_text.lower() != active_npc.lower():
            errors.append(f"Dialogue mode: speaker must be current_npc '{active_npc}'.")
        if current_choice_text and reply_text.lower() == current_choice_text:
            errors.append("Dialogue mode: reply must not repeat the player's selected line verbatim.")

        raw_choices = parsed.get("choices")
        if not isinstance(raw_choices, list):
            errors.append("Key 'choices' must be list")
            raw_choices = []

        cleaned_choices = []
        seen_choice_ids = set()
        for idx, raw_choice in enumerate(raw_choices[:MAX_LLM_CHOICES], start=1):
            choice = self._normalise_choice(raw_choice, fallback_index=idx)
            if not choice:
                continue
            key = self._choice_key(choice)
            if key in seen_choice_ids:
                continue
            seen_choice_ids.add(key)
            cleaned_choices.append(choice)

        while len(cleaned_choices) < MIN_LLM_CHOICES: #If the LLM gives not enough choices, we add some generic ones to try and get out of the loop
            progress = self._build_progress_choice({self._choice_key(choice) for choice in cleaned_choices})
            if self._choice_key(progress) in {self._choice_key(choice) for choice in cleaned_choices}:
                break
            cleaned_choices.append(progress)

        cleaned_choices = self._enforce_progress_choice(cleaned_choices)
        cleaned_choices = self._inject_story_choice(cleaned_choices)
        if not (MIN_LLM_CHOICES <= len(cleaned_choices) <= MAX_LLM_CHOICES):
            errors.append(f"choices must contain between {MIN_LLM_CHOICES} and {MAX_LLM_CHOICES} items")

        cleaned_updates, update_errors = self._sanitize_state_updates(parsed.get("state_updates", {}))
        errors.extend(update_errors)

        memory_summary = parsed.get("memory_summary", "")
        if not isinstance(memory_summary, str):
            memory_summary = ""
        memory_summary = memory_summary.strip()
        if not memory_summary:
            memory_summary = self._build_auto_memory_summary(speaker_text, reply_text)

        arc_update, arc_errors = self._sanitize_arc_update(parsed.get("arc_update", {}))
        errors.extend(arc_errors)

        event_type = str(parsed.get("event_type", "dialogue")).strip().lower() or "dialogue"
        if event_type not in ALLOWED_EVENT_TYPES:
            event_type = "dialogue"

        raw_tags = parsed.get("tags", [])
        clean_tags = []
        if isinstance(raw_tags, list):
            for raw_tag in raw_tags:
                tag = self._slugify(raw_tag)
                if tag and tag not in clean_tags:
                    clean_tags.append(tag)
        if not clean_tags:
            clean_tags = self._derive_tags(reply_text, memory_summary)

        raw_importance = parsed.get("importance")
        if isinstance(raw_importance, bool) or not isinstance(raw_importance, int):
            importance = self._estimate_importance(event_type, cleaned_updates, arc_update)
        else:
            importance = max(0, min(10, raw_importance))

        if errors:
            return False, None, errors

        parsed["narrator"] = narrator_text
        parsed["speaker"] = speaker_text
        parsed["reply"] = reply_text
        parsed["choices"] = cleaned_choices
        parsed["state_updates"] = cleaned_updates
        parsed["memory_summary"] = memory_summary
        parsed["arc_update"] = arc_update
        parsed["event_type"] = event_type
        parsed["tags"] = clean_tags[:6]
        parsed["importance"] = importance
        return True, parsed, []

    def _log_turn(self, player_choice, prompt_text, raw_output, parsed_output, valid, errors):
        row = {
            "timestamp": time.time(),
            "mode": "llm",
            "model": self.llm.model_id,
            "turn": self.turn,
            "player_choice_id": player_choice.get("id"),
            "player_choice_text": player_choice.get("text"),
            "player_action_type": player_choice.get("action_type"),
            "prompt": prompt_text,
            "prompt_tokens": self.last_retrieval.get("prompt_tokens", 0),
            "memory_tokens": self.last_retrieval.get("memory_tokens", 0),
            "retrieval_query": self.last_retrieval.get("query", {}),
            "retrieval_candidate_count": self.last_retrieval.get("candidate_count", 0),
            "retrieved_memory_ids": [item.get("event_id") for item in self.last_retrieval.get("selected", [])],
            "retrieval_scores": [
                {
                    "event_id": item.get("event_id"),
                    "score": round(float(item.get("score", 0.0)), 4),
                    "token_count": item.get("token_count"),
                }
                for item in self.last_retrieval.get("selected", [])
            ],
            "raw_output": raw_output,
            "parsed_output": parsed_output,
            "valid": valid,
            "errors": errors,
        }
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    def _build_retrieval_query(self, player_choice):
        active_quest_ids = sorted(self.world_state.get("active_quests", {}).keys())
        recent_dialogue = []
        last_player_action = self.world_state.get("last_player_action")
        last_reply = self.world_state.get("last_reply")
        if isinstance(last_player_action, str) and last_player_action.strip():
            recent_dialogue.append(last_player_action.strip())
        if isinstance(last_reply, str) and last_reply.strip():
            recent_dialogue.append(last_reply.strip())
        keywords = sorted(
            self._tokenize_for_match(
                " ".join(
                    [
                        str(player_choice.get("id", "")),
                        str(player_choice.get("text", "")),
                        str(self.current_npc or ""),
                        " ".join(active_quest_ids),
                        " ".join(recent_dialogue),
                    ]
                )
            )
        )
        return {
            "choice_id": player_choice.get("id"),
            "choice_text": player_choice.get("text"),
            "action_type": player_choice.get("action_type"),
            "current_npc": self.current_npc,
            "active_quest_ids": active_quest_ids,
            "recent_dialogue": recent_dialogue[-4:],
            "keywords": keywords,
        }

    def _score_memory_candidate(self, event, query):
        event_id = str(event.get("event_id", "")).strip() or f"legacy_{event.get('turn', 0)}"
        quest_ids = {str(item).strip() for item in event.get("quest_ids", []) if str(item).strip()}
        tag_terms = set()
        for raw_tag in event.get("tags", []):
            tag_terms.update(self._tokenize_for_match(raw_tag))
        text_terms = self._tokenize_for_match(
            " ".join(
                [
                    str(event.get("memory_summary", "")),
                    str(event.get("reply", "")),
                    str(event.get("choice_text", "")),
                    str(event.get("choice_id", "")),
                ]
            )
        )
        query_terms = set(query.get("keywords", [])) #Finding an overlap between the query adn the memory candidate
        quest_overlap = quest_ids & set(query.get("active_quest_ids", []))
        keyword_overlap = query_terms & (tag_terms | text_terms)
        same_npc = str(event.get("current_npc", "")).strip().lower() == str(query.get("current_npc", "")).strip().lower()
        turns_ago = max(0, self.turn - int(event.get("turn", 0) or 0))
        recency_score = 1.0 / (1 + turns_ago)
        importance = event.get("importance", 3)
        if isinstance(importance, bool) or not isinstance(importance, int):
            importance = 3
        importance_score = max(0, min(10, importance)) / 10.0
        event_type = str(event.get("event_type", "dialogue")).strip().lower()
        if event_type == "fallback":
            importance_score *= 0.4
        constraint_bonus = 0.0
        if quest_overlap:
            constraint_bonus += 1.5
        if same_npc:
            constraint_bonus += 0.35
        if event_type in {"promise", "debt", "threat"} and same_npc:
            constraint_bonus += 0.75
        score = len(keyword_overlap) * 1.25 + recency_score + importance_score + constraint_bonus
        return {
            "event_id": event_id,
            "event": event,
            "score": score,
            "passes_filter": bool(keyword_overlap or quest_overlap or same_npc),
        }

    def _retrieve_memories(self, player_choice): #Loading and then also scoring them to find the most relevant memories  
        query = self._build_retrieval_query(player_choice)
        npc_turns = self.memory_store.load_npc_turns(self.current_npc, MEMORY_NPC_TURNS)
        recent = self.memory_store.load_recent_turns(MEMORY_RECENT_TURNS)

        seen_ids = set()
        combined = []
        for event in npc_turns + recent:
            event_id = str(event.get("event_id", "")).strip() or f"legacy_{event.get('turn', 0)}_{len(combined)}"
            if event_id in seen_ids:
                continue
            seen_ids.add(event_id)
            combined.append(event)

        scored = []
        for event in combined:
            item = self._score_memory_candidate(event, query)
            if item["passes_filter"]:
                scored.append(item)
        if not scored:
            for event in combined[-MEMORY_RECENT_TURNS:]:
                scored.append(self._score_memory_candidate(event, query))
        scored.sort(key=lambda item: item["score"], reverse=True)

        selected = []
        summaries = []
        memory_tokens = 0 #Keeping track of how many tokens being used 
        for item in scored:
            summary = str(item["event"].get("memory_summary", "")).strip()
            if not summary:
                summary = self._build_auto_memory_summary(
                    str(item["event"].get("speaker", "")),
                    str(item["event"].get("reply", "")),
                )
            token_count = self._safe_token_count(summary)
            if selected and memory_tokens + token_count > MEMORY_TOKEN_BUDGET:
                continue
            item["token_count"] = token_count
            selected.append(item)
            summaries.append(summary)
            memory_tokens += token_count
            if len(selected) >= MEMORY_TOP_K:
                break

        self.last_retrieval = {
            "query": query,
            "selected": selected,
            "candidate_count": len(combined),
            "memory_tokens": memory_tokens,
            "prompt_tokens": 0,
        }
        return summaries

    def _build_prompt(self, player_choice):
        recent = self.messages[-4:]
        if recent:
            recent_text = "\n".join(f"{m['role']}: {m['content']}" for m in recent)
        else:
            recent_text = "none"

        state_slice = { #Giving the LLM a small snapshot of the current state
            "current_location": self.current_location,
            "current_npc": self.current_npc,
            "time_of_day": self.world_state.get("time_of_day", "night"),
            "day": self.world_state.get("day", 1),
            "active_quests": self.world_state.get("active_quests", {}),
            "quest_flags": self.world_state.get("quest_flags", {}),
            "inventory": self.world_state.get("inventory", []),
            "npc_relationships": self.world_state.get("npc_relationships", {}),
            "last_memory_summary": self.last_memory_summary,
        }

        memories = self._retrieve_memories(player_choice) #Retrieving 'relevant' memories to give the LLM next
        if memories:
            memory_block = "\n".join(f"- {s}" for s in memories)
        else:
            memory_block = "none"

        arc_state = self._current_arc_state()
        known_npcs = sorted(set(self._known_npc_map().values()))
        known_locations = sorted(set(self._known_location_map().values()))
        known_quests = sorted(self.world_state.get("active_quests", {}).keys())
        known_flags = sorted(self.world_state.get("quest_flags", {}).keys())

        prompt = (
            f"{self.prompt_template}\n\n" 
            f"{self.prologue_summary}\n\n" 
            "HARD FACTS:\n" 
            f"{json.dumps(state_slice)}\n\n"
            "PLAYER ACTION:\n"
            f"- choice_id: {player_choice.get('id')}\n"
            f"- action_type: {player_choice.get('action_type')}\n"
            f"- spoken_text: {player_choice.get('text')}\n\n"
            "ARC GOAL:\n"
            f"- phase: {arc_state.get('phase')}\n"
            f"- next_required_beat: {arc_state.get('next_required_beat') or 'none'}\n"
            f"- next_required_goal: {arc_state.get('next_required_goal')}\n"
            f"- beat_deadline_turn: {arc_state.get('beat_deadline_turn')}\n"
            f"- steering_strength: {arc_state.get('steering_strength', 'soft')}\n"
            f"- completed_beats: {', '.join(arc_state.get('completed_beats', [])) or 'none'}\n\n"
            "RELEVANT MEMORIES:\n"
            f"{memory_block}\n\n"
            "RECENT CONTEXT:\n"
            f"{recent_text}\n\n"
            f"Turn: {self.turn}\n"
            f"Current NPC: {self.current_npc}\n"
            f"Current location: {self.current_location}\n"
            "WORLD CONSISTENCY RULES:\n"
            f"- only use these state_updates keys: {', '.join(sorted(ALLOWED_STATE_UPDATE_KEYS))}\n"
            "- use state_updates only for small ambient changes such as time passing.\n"
            "- do not change quest status, inventory, current_npc, or current_location in state_updates.\n"
            f"- active NPCs in this scene are: {', '.join(known_npcs) if known_npcs else 'none'}\n"
            f"- known locations are: {', '.join(known_locations) if known_locations else 'none'}\n"
            f"- active quest ids in memory are: {', '.join(known_quests) if known_quests else 'none'}\n"
            f"- quest flags currently tracked are: {', '.join(known_flags) if known_flags else 'none'}\n"
            f"- time_of_day must be one of: {', '.join(sorted(VALID_TIME_OF_DAY))}\n\n"
            "CHOICE QUALITY GUARDRAILS:\n"
            "- choices must be 2-3 unique objects with id, text, action_type.\n"
            "- if choices are repeating from the previous turn, replace one with a concrete next-step question.\n"
            "- include at least one concrete lead, travel, or evidence-focused next step when possible."
        )
        self.last_retrieval["prompt_tokens"] = self._safe_token_count(prompt)
        return prompt

    def _apply_arc_update(self, parsed_output):
        arc_state = self._current_arc_state()
        deadline_turn = arc_state.get("beat_deadline_turn")
        arc_state["steering_strength"] = "soft"
        if deadline_turn is not None and self.turn + 1 >= int(deadline_turn):
            arc_state["steering_strength"] = "hard"
        self.world_state["arc_state"] = arc_state

    def _apply_state_updates(self, player_choice, parsed_output): #Taking the updates from the LLM and applying them to our world state
        updates = parsed_output.get("state_updates")
        if not isinstance(updates, dict):
            updates = {}

        new_time = updates.get("time_of_day") #Time update
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

        #Updating the world state with everything we have at the end of turn
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

    def _persist_turn_memory(self, player_choice, parsed_output):
        # Save "last visible output" so resume can show context to the player.
        self.world_state["last_narrator"] = parsed_output["narrator"]
        self.world_state["last_speaker"] = parsed_output["speaker"]
        self.world_state["last_reply"] = parsed_output["reply"]
        self.world_state["last_choices"] = list(parsed_output["choices"])

        # Save canonical snapshot.
        self.state_store.save(self.world_state)

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
            "memory_summary": parsed_output.get("memory_summary", ""),
            "state_updates": parsed_output.get("state_updates", {}),
            "arc_update": parsed_output.get("arc_update", {}),
            "event_type": parsed_output.get("event_type", "dialogue"),
            "tags": parsed_output.get("tags", []),
            "importance": parsed_output.get("importance", 3),
            "quest_ids": sorted(self.world_state.get("active_quests", {}).keys()),
            "retrieved_memory_ids": [item.get("event_id") for item in self.last_retrieval.get("selected", [])],
            "retrieval_scores": [
                {
                    "event_id": item.get("event_id"),
                    "score": round(float(item.get("score", 0.0)), 4),
                }
                for item in self.last_retrieval.get("selected", [])
            ],
            "rule_effects": self.last_rule_effects,
        }
        self.memory_store.append_turn(event)
        self.memory_store.append_npc_memory(parsed_output.get("speaker"), event)

    def _show_resume_context(self):
        #Printing context so the user can see where they are resuming from
        print(f"Resumed at {self.current_location} with {self.current_npc}.")

        last_action = self.world_state.get("last_player_action")
        if isinstance(last_action, str) and last_action.strip():
            print(f"Most recent player action: {last_action}")

        narrator = self.world_state.get("last_narrator")
        speaker = self.world_state.get("last_speaker")
        reply = self.world_state.get("last_reply")
        choices = self.world_state.get("last_choices")

        if not narrator or not speaker: #Try loading from memory if not in world state
            last_turn = self.memory_store.load_last_turn()
            if isinstance(last_turn, dict):
                narrator = narrator or last_turn.get("narrator")
                speaker = speaker or last_turn.get("speaker")
                reply = reply or last_turn.get("reply")
                choices = choices or last_turn.get("choices")

        if isinstance(narrator, str) and narrator.strip():
            type_line(f"Narrator: {narrator}")
        if isinstance(speaker, str) and speaker.strip() and isinstance(reply, str) and reply.strip():
            type_line(f"{speaker}: {reply}")

        if isinstance(choices, list) and choices: #showing the choices that were available atthe end of the last session
            self.last_choices = self._coerce_choice_list(choices)
            type_line("Most recent choices were:")
            for i, choice in enumerate(self.last_choices, start=1):
                type_line(f"  {i}. {choice['text']}")

    def _build_fallback_output(self, last_errors):
        blocked = {self._choice_key(choice) for choice in self.last_choices}
        progress = self._build_progress_choice(blocked)
        follow_up = {
            "id": "ask_for_single_fact",
            "text": "Then give me the single most useful fact you do know.",
            "action_type": "ask",
        }
        if self._choice_key(follow_up) in blocked:
            follow_up = {
                "id": "restate_next_step",
                "text": "Point me to the next place I should check.",
                "action_type": "travel",
            }
        reply = (
            "Give me a moment. I can stay useful if we focus on one concrete lead, one witness, "
            "or one place to inspect next."
        )
        memory_summary = f"Fallback response used while speaking with {self.current_npc} at {self.current_location}."
        return {
            "narrator": "",
            "speaker": str(self.current_npc or "NPC").strip() or "NPC",
            "reply": reply,
            "choices": [progress, follow_up],
            "state_updates": {},
            "memory_summary": memory_summary,
            "arc_update": {"advance": False, "beat_id": "", "reason": "fallback"},
            "event_type": "fallback",
            "tags": self._derive_tags(reply, memory_summary),
            "importance": 2,
            "fallback_errors": list(last_errors),
        }

    def _generate_valid_json(self, prompt_text): #Generating the json output and some schema validation
        history = self.messages[-self.max_history_messages:]
        base_messages = history + [{"role": "user", "content": prompt_text}]
        last_raw = ""
        last_errors = []

        for attempt in range(1, MAX_JSON_RETRY_ATTEMPTS + 1):
            if attempt == 1:
                attempt_messages = base_messages
            else:
                arc_state = self._current_arc_state()
                repair_message = {
                    "role": "user",
                    "content": (
                        "Your last response was invalid. Return ONLY valid JSON.\n"
                        f"Fix these errors exactly: {json.dumps(last_errors)}\n"
                        f"Use this exact speaker value: {self.current_npc}\n"
                        "Never set speaker to Alex.\n"
                        "Do not repeat the player's selected line in reply.\n"
                        "Choices must be 2-3 objects with keys id, text, action_type.\n"
                        "Do not change quest status, inventory, current_npc, or current_location in state_updates.\n"
                        f"Current beat: {arc_state.get('next_required_beat') or 'none'}.\n"
                        "No markdown fences. No explanation. JSON object only."
                    ),
                }
                attempt_messages = base_messages + [repair_message]

            raw = self.llm.generate(attempt_messages)
            last_raw = raw
            parsed = self._extract_json_object(raw)
            valid, parsed_output, errors = self._validate_output(parsed)
            if valid:
                out_errors = []
                if attempt > 1:
                    out_errors.append(f"json_retry_attempt_{attempt}")
                return raw, parsed_output, True, out_errors

            last_errors = errors
        fallback_output = self._build_fallback_output(last_errors)
        return last_raw, fallback_output, True, [f"fallback_used_after_{MAX_JSON_RETRY_ATTEMPTS}_attempts"] + last_errors

    def run(self): #The main loop for runnning the LLM
        print("Dynamic mode enabled. LLM is active.")
        if self.resume_mode:
            self._show_resume_context()
            if self.last_choices:
                print("Select a choice to continue.")
                player_choice = self._prompt_for_choice()
                if player_choice is None:
                    return
            else:
                player_choice = {
                    "id": self.world_state.get("last_choice_id", "continue_investigation"),
                    "text": self.world_state.get(
                        "last_choice_text",
                        self.world_state.get("last_player_action", "I continue the investigation."),
                    ),
                    "action_type": "resume",
                }
        else:
            player_choice = dict(self.initial_player_choice)

        while True:
            self.turn += 1
            self._apply_story_choice_rules(player_choice)
            self.current_player_choice = dict(player_choice)
            prompt_text = self._build_prompt(player_choice)

            print(self._thinking_label())
            raw_output, parsed_output, valid, errors = self._generate_valid_json(prompt_text)

            self._log_turn(
                player_choice,
                prompt_text,
                raw_output,
                parsed_output,
                valid,
                errors,
            )

            if not valid:
                print("Session ended: model could not produce a valid turn.")
                return

            self.messages.append({"role": "user", "content": f"{player_choice.get('id')}: {player_choice.get('text')}"})
            self.last_memory_summary = parsed_output["memory_summary"]
            if parsed_output["narrator"]:
                type_line(f"Narrator: {parsed_output['narrator']}")
            if parsed_output["speaker"] and parsed_output["reply"]:
                type_line(f"{parsed_output['speaker']}: {parsed_output['reply']}")
            self.messages.append({"role": "assistant", "content": f"{parsed_output['speaker']}: {parsed_output['reply']}"})
            self.last_choices = parsed_output["choices"]
            for i, choice in enumerate(self.last_choices, start=1):
                type_line(f"  {i}. {choice['text']}")

            self._apply_state_updates(player_choice, parsed_output)
            self._persist_turn_memory(player_choice, parsed_output)

            #Pausing after the response, not overwhelming, easy to read
            if POST_RESPONSE_PAUSE_SECONDS > 0:
                time.sleep(POST_RESPONSE_PAUSE_SECONDS)

            player_choice = self._prompt_for_choice()
            if player_choice is None:
                return

