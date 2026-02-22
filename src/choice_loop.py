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


PROMPT_PATH = Path("prompts/prompt_v1.txt")
LOG_PATH = Path("dialogue_log.jsonl")
LLM_THOUGHT_SECONDS = 3


class ChoiceLoop:
    def __init__(self, llm, prologue_summary, initial_player_action, current_npc, current_location):
        self.llm = llm
        self.prologue_summary = prologue_summary
        self.initial_player_action = initial_player_action
        self.current_npc = current_npc
        self.current_location = current_location
        self.last_memory_summary = "Investigation has just entered dynamic mode."
        self.prompt_template = self._load_prompt_template()
        self.messages = [
            {
                "role": "system",
                "content": "You are a grounded fantasy NPC narrator. Keep replies short and specific.",
            }
        ]
        self.turn = 0
        self.last_choices = []
        self.max_history_messages = 6

    def _llm_thinking_pause(self):
        #Small pause to simulate thinking
        print("LLM is thinking...")
        time.sleep(LLM_THOUGHT_SECONDS)

    def _safe_input(self, label):
        try:
            return input(label).strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSession ended.")
            return None

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
        
        choices = parsed["choices"] #Clean the choices ensuring they are strings
        cleaned = []
        for choice in choices[:4]:
            if isinstance(choice, str):
                text = choice.strip()
            elif isinstance(choice, dict):
                text = str(choice.get("text", "")).strip()
            else:
                text = str(choice).strip()
            if text:
                cleaned.append(text)

        if not (2 <= len(cleaned) <= 4):
            return False, None, ["choices must contain 2-4 non-empty items"]

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
        #Commit 4
        #1 base contract from prompt_v1.txt
        #2 prologue summary
        #3 short recent context from chat history
        #4 current player input
        recent = self.messages[-4:]
        if recent:
            recent_text = "\n".join(f"{m['role']}: {m['content']}" for m in recent)
        else:
            recent_text = "none"

        return (
            f"{self.prompt_template}\n\n"
            f"{self.prologue_summary}\n\n"
            "Recent context:\n"
            f"{recent_text}\n\n"
            f"Turn: {self.turn}\n"
            f"Current NPC: {self.current_npc}\n"
            f"Current location: {self.current_location}\n"
            f"Player input: {player_input}\n\n"
            "Return JSON only."
        )

    def _generate_valid_json(self, prompt_text): #Generating the json output and some schema validation
        history = self.messages[-self.max_history_messages:]
        local_messages = history + [{"role": "user", "content": prompt_text}]
        raw = self.llm.generate(local_messages)
        parsed = self._extract_json_object(raw)
        valid, parsed_output, errors = self._validate_output(parsed)

        if valid:
            return raw, parsed_output, True, []

        retry_messages = local_messages + [
            {
                "role": "user",
                "content": (
                    "Your last response was invalid. Return ONLY valid JSON with exactly this shape:\n"
                    "{\"narrator\":\"...\",\"speaker\":\""
                    + self.current_npc
                    + "\",\"reply\":\"...\",\"choices\":[\"...\",\"...\"],\"state_updates\":{},\"memory_summary\":\"...\"}"
                ),
            }
        ]
        retry_raw = self.llm.generate(retry_messages)
        retry_parsed = self._extract_json_object(retry_raw)
        retry_valid, retry_output, retry_errors = self._validate_output(retry_parsed)

        if retry_valid:
            return retry_raw, retry_output, True, []

        return retry_raw, None, False, retry_errors

    def run(self): #The main loop for runnning the LLM
        print("Dynamic mode enabled. LLM is active.")
        player_input = self.initial_player_action

        while True:
            self.turn += 1
            prompt_text = self._build_prompt(player_input)

            print("LLM is thinking...")
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
                print("Session ended: no fallback mode.")
                break

            self.messages.append({"role": "user", "content": player_input})
            self.messages.append({"role": "assistant", "content": json.dumps(parsed_output)})
            self.last_memory_summary = parsed_output["memory_summary"]

            print(f"Narrator: {parsed_output['narrator']}")
            self._llm_thinking_pause()
            print(f"{parsed_output['speaker']}: {parsed_output['reply']}")
            self._llm_thinking_pause()
            self.last_choices = parsed_output["choices"]
            for i, text in enumerate(self.last_choices, start=1):
                print(f"  {i}. {text}")
                self._llm_thinking_pause()

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
                    player_input = self.last_choices[idx - 1]
                    break 
                print("Invalid choice number. Try again.") 