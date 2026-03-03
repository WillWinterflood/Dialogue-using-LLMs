'''
src/choice_loop.py

Choice-driven dynamic loop:
- build constrained prompt
- generate JSON
- validate minimal schema
- log each turn
- print NPC dialogue and next choices
'''

import json
import time
from pathlib import Path
from src.text_fx import type_line #Typewriter thing as it makes it look better


PROMPT_PATH = Path("prompts/prompt_v1.txt")
LOG_PATH = Path("dialogue_log.jsonl")
POST_RESPONSE_PAUSE_SECONDS = 0.2 # Small pause to allow for reading
PLAYER_CHOICE_SPEAK_SECONDS = 0.2
MAX_JSON_RETRY_ATTEMPTS = 6
LLM_CHOICES_PER_TURN = 2


class ChoiceLoop:
    def __init__(
        self,
        llm,
        prologue_summary,
        initial_player_action,
        current_npc,
        current_location,
        world_state,
        state_store,
        memory_store,
        resume_mode=False,
    ):
        self.llm = llm
        self.prologue_summary = prologue_summary
        self.initial_player_action = initial_player_action
        self.world_state = world_state
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
        self.last_choices = []
        self.max_history_messages = 6
        self.current_player_input = "" #Tracking the latest input

    def _safe_input(self, label):
        try:
            return input(label).strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSession ended.")
            return None

    def _normalize_choice_text(self, raw_text): #Cleaning up the LLM output
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

    def _select_choice_from_number(self, raw_text):
        text = str(raw_text or "").strip()
        if not text.isdigit():
            return text
        if not self.last_choices:
            return text
        idx = int(text)
        if not (1 <= idx <= len(self.last_choices)):
            return text

        selected = self.last_choices[idx - 1]
        spoken = self._normalize_choice_text(selected)
        print("Alex is thinking...")
        if PLAYER_CHOICE_SPEAK_SECONDS > 0:
            time.sleep(PLAYER_CHOICE_SPEAK_SECONDS)
        type_line(f"Alex: {spoken or selected}")
        return spoken or selected

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

    def _validate_output(self, parsed): #Ensure it has the correct types
        if not isinstance(parsed, dict):
            return False, None, ["Output is not a JSON object."]

        required = {
            "narrator": str,
            "speaker": str,
            "reply": str,
            "choices": list,
            "state_updates": dict,
            "memory_summary": str,
        }

        errors = []
        for key, expected_type in required.items():
            if key not in parsed:
                errors.append(f"Missing required key: {key}")
                continue
            if not isinstance(parsed[key], expected_type):
                errors.append(f"Key '{key}' must be {expected_type.__name__}")

        if errors:
            return False, None, errors

        narrator_text = parsed["narrator"].strip()
        speaker_text = parsed["speaker"].strip()
        reply_text = parsed["reply"].strip()
        active_npc = str(self.current_npc or "").strip()

        if not speaker_text or not reply_text:
            return False, None, ["Dialogue mode: speaker and reply must both be non-empty."]
        if active_npc and speaker_text.lower() != active_npc.lower():
            return False, None, [f"Dialogue mode: speaker must be current_npc '{active_npc}'."]
        current_input = str(self.current_player_input or "").strip().lower()
        if current_input and reply_text.lower() == current_input:
            return False, None, ["Dialogue mode: reply must not repeat the player's line verbatim."]

        parsed["narrator"] = narrator_text
        parsed["speaker"] = speaker_text
        parsed["reply"] = reply_text

        choices = parsed["choices"] #Clean the choices ensuring they are strings
        cleaned = []
        for choice in choices[:LLM_CHOICES_PER_TURN]:
            if isinstance(choice, str):
                text = choice.strip()
            elif isinstance(choice, dict):
                text = str(choice.get("text", "")).strip()
            else:
                text = str(choice).strip()
            if text:
                tagged = self._normalize_choice_text(text)
                if tagged:
                    cleaned.append(tagged)

        # Remove duplicates while preserving order.
        deduped = []
        seen = set()
        for c in cleaned:
            key = c.lower().strip()
            if key and key not in seen:
                seen.add(key)
                deduped.append(c)
        cleaned = deduped

        if len(cleaned) != LLM_CHOICES_PER_TURN:
            return False, None, [f"choices must contain exactly {LLM_CHOICES_PER_TURN} non-empty items"]

        parsed["choices"] = cleaned
        return True, parsed, []

    def _log_turn(self, user_text, prompt_text, raw_output, parsed_output, valid, errors):
        row = {
            "timestamp": time.time(),
            "model": self.llm.model_id,
            "turn": self.turn,
            "user_input": user_text,
            "prompt": prompt_text,
            "raw_output": raw_output,
            "parsed_output": parsed_output,
            "valid": valid,
            "errors": errors,
        }
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    def _build_prompt(self, player_input):
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

        return (
            f"{self.prompt_template}\n\n" 
            f"{self.prologue_summary}\n\n" 
            "Canonical world state:\n" 
            f"{json.dumps(state_slice)}\n\n"
            "Recent context:\n"
            f"{recent_text}\n\n"
            f"Turn: {self.turn}\n"
            f"Current NPC: {self.current_npc}\n"
            f"Current location: {self.current_location}\n"
            f"Player input: {player_input}"
        )

    def _apply_state_updates(self, player_input, parsed_output): #Taking the updates from the LLM and applying them to our world state
        #This can be imrpoved by making the LLM know what NPCs, locations, day etc... it actually has
        updates = parsed_output.get("state_updates")
        if not isinstance(updates, dict):
            updates = {}

        #updates for location/NPC/quest/relationships, going to implement later

        new_time = updates.get("time_of_day") #Time update
        if isinstance(new_time, str) and new_time.strip():
            self.world_state["time_of_day"] = new_time.strip()

        new_day = updates.get("day")
        if isinstance(new_day, int) and new_day > 0:
            self.world_state["day"] = new_day

        inv = self.world_state.get("inventory", [])
        add_items = updates.get("inventory_add")
        if isinstance(add_items, list):
            for item in add_items:
                text = str(item).strip()
                if text and text not in inv:
                    inv.append(text)

        remove_items = updates.get("inventory_remove")
        if isinstance(remove_items, list):
            for item in remove_items:
                text = str(item).strip()
                if text in inv:
                    inv.remove(text)
        self.world_state["inventory"] = inv
        
        #Updating the world state with everything we have at the end of turn
        self.world_state["current_location"] = self.current_location
        self.world_state["current_npc"] = self.current_npc
        self.world_state["last_player_action"] = player_input
        self.world_state["last_memory_summary"] = parsed_output.get("memory_summary", "")
        self.world_state["turn"] = self.turn

    def _persist_turn_memory(self, player_input, parsed_output):
        # Save "last visible output" so resume can show context to the player.
        self.world_state["last_narrator"] = parsed_output["narrator"]
        self.world_state["last_speaker"] = parsed_output["speaker"]
        self.world_state["last_reply"] = parsed_output["reply"]
        self.world_state["last_choices"] = list(parsed_output["choices"])

        # Save canonical snapshot.
        self.state_store.save(self.world_state)

        event = {
            "timestamp": time.time(),
            "turn": self.turn,
            "player_input": player_input,
            "narrator": parsed_output["narrator"],
            "speaker": parsed_output["speaker"],
            "reply": parsed_output["reply"],
            "choices": parsed_output["choices"],
            "current_npc": self.current_npc,
            "current_location": self.current_location,
            "memory_summary": parsed_output.get("memory_summary", ""),
            "state_updates": parsed_output.get("state_updates", {}),
        }
        self.memory_store.append_turn(event)
        self.memory_store.append_npc_memory(self.current_npc, event)

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
            self.last_choices = []
            for choice in choices:
                tagged = self._normalize_choice_text(choice)
                if tagged:
                    self.last_choices.append(tagged)
            type_line("Most recent choices were:")
            for i, text in enumerate(self.last_choices, start=1):
                if str(text).strip():
                    type_line(f"  {i}. {str(text).strip()}")

    def _generate_valid_json(self, prompt_text): #Generating the json output and some schema validation
        history = self.messages[-self.max_history_messages:]
        base_messages = history + [{"role": "user", "content": prompt_text}]
        last_raw = ""
        last_errors = []

        for attempt in range(1, MAX_JSON_RETRY_ATTEMPTS + 1):
            if attempt == 1:
                attempt_messages = base_messages
            else:
                repair_message = {
                    "role": "user",
                    "content": (
                        "Your last response was invalid. Return ONLY valid JSON.\n"
                        "Fix these errors exactly:\n"
                        f"{json.dumps(last_errors)}\n"
                        "Required pattern:\n"
                        "1) Dialogue turn only: narrator may be empty, speaker+reply must be non-empty.\n"
                        "Required keys are: narrator, speaker, reply, choices, state_updates, memory_summary.\n"
                        "Choices must contain exactly two short spoken lines Alex can say out loud.\n"
                        f"Use this exact speaker value: {self.current_npc}\n"
                        "Never set speaker to Alex.\n"
                        "Do not repeat the player's line in reply.\n"
                        "Minimal valid shape:\n"
                        f"{{\"narrator\":\"\",\"speaker\":\"{self.current_npc}\",\"reply\":\"short line\",\"choices\":[\"choice 1\",\"choice 2\"],\"state_updates\":{{}},\"memory_summary\":\"one sentence\"}}\n"
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

        final_errors = [f"json_validation_failed_after_{MAX_JSON_RETRY_ATTEMPTS}_attempts"] + last_errors
        return last_raw, None, False, final_errors

    def run(self): #The main loop for runnning the LLM
        print("Dynamic mode enabled. LLM is active.")
        if self.resume_mode:
            self._show_resume_context()
            print("Type your next action.")
            first_input = self._safe_input("You > ")
            if first_input is None:
                return
            player_input = self._select_choice_from_number(first_input)
        else:
            player_input = self.initial_player_action

        while True:
            self.turn += 1
            self.current_player_input = player_input
            prompt_text = self._build_prompt(player_input)

            print(self._thinking_label())
            raw_output, parsed_output, valid, errors = self._generate_valid_json(prompt_text)

            self._log_turn(
                player_input,
                prompt_text,
                raw_output,
                parsed_output,
                valid,
                errors,
            )

            if not valid:
                print("LLM > (invalid JSON output)")
                print(f"Errors: {errors}")
                print("Session ended: model could not produce valid JSON after retries.")
                break

            self.messages.append({"role": "user", "content": player_input})
            self.messages.append({"role": "assistant", "content": json.dumps(parsed_output)})
            self.last_memory_summary = parsed_output["memory_summary"]
            if parsed_output["narrator"]:
                type_line(f"Narrator: {parsed_output['narrator']}")
            if parsed_output["speaker"] and parsed_output["reply"]:
                type_line(f"{parsed_output['speaker']}: {parsed_output['reply']}")
            self.last_choices = parsed_output["choices"]
            for i, text in enumerate(self.last_choices, start=1):
                type_line(f"  {i}. {text}")

            self._apply_state_updates(player_input, parsed_output)
            self._persist_turn_memory(player_input, parsed_output)

            #Pausing after the response, not overwhelming, easy to read
            if POST_RESPONSE_PAUSE_SECONDS > 0:
                time.sleep(POST_RESPONSE_PAUSE_SECONDS)

            while True:
                choice_raw = self._safe_input("Choice > ")
                if choice_raw is None:
                    return
                if choice_raw.lower() in {"/quit", "/exit"}:
                    print("Session ended.")
                    return
                if not choice_raw.isdigit():
                    print("Please choose by number.")
                    continue

                idx = int(choice_raw) #
                if 1 <= idx <= len(self.last_choices):
                    player_input = self._select_choice_from_number(choice_raw)
                    break 
                print("Invalid choice number. Try again.")  

