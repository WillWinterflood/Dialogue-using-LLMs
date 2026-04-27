"""
src/choice_loop.py

Thin conductor for the dynamic dialogue loop.
It handles player-facing I/O and delegates prompt building, validation,
retrieval, state mutation, and logging to focused modules.
"""
#For the logging files
import time

from src.choice_formatter import _coerce_choice_list
from src.config import PLAYER_CHOICE_SPEAK_SECONDS, POST_RESPONSE_PAUSE_SECONDS
from src.memory_retrieval import _retrieve_memories
from src.output_validator import OutputValidationExhausted, _generate_valid_json
from src.prompt_builder import _build_prompt, _load_prompt_template
from src.state_manager import StateManager
from src.story_rules import forced_story_choices, suggest_story_choices
from src.text_fx import type_line
from src.turn_logger import _log_failure, _log_turn

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
        self.memory_store = memory_store
        self.resume_mode = resume_mode
        self.state = StateManager(
            world_state,
            state_store,
            memory_store,
            current_npc=current_npc,
            current_location=current_location,
            llm=self.llm,  # Needed for LLM importance rating and reflection
        )
        self.prompt_template = _load_prompt_template()
        self.messages = [
            {
                "role": "system",
                "content": "You are a grounded fantasy NPC narrator. Keep replies short and specific.",
            }
        ]
        self.last_choices = _coerce_choice_list(self.state.world_state.get("last_choices", []))
        self.current_player_choice = {}
        self.last_retrieval = {
            "query": {},
            "selected": [],
            "candidate_count": 0,
            "memory_tokens": 0,
            "prompt_tokens": 0,
        }
        self.choice_timer_started_at = None

    def _visible_turn_number(self):
        try:
            handoff_turns = int(self.state.world_state.get("handoff_turn_index", 0) or 0)
        except Exception:
            handoff_turns = 0
        return handoff_turns + self.state.turn

    def _show_turn_marker(self, turn_number=None): #Showing turn marker for human evaluation
        visible_turn = self._visible_turn_number() 
        if turn_number is None: 
            visible_turn = self._visible_turn_number()
        else:
            visible_turn = int(turn_number)

        print(f"[Turn {visible_turn}]")

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
        self.choice_timer_started_at = time.perf_counter()
        print("Alex is thinking...")
        if PLAYER_CHOICE_SPEAK_SECONDS > 0:
            time.sleep(PLAYER_CHOICE_SPEAK_SECONDS)
        type_line(f"Alex: {selected['text']}")
        return selected

    def _thinking_label(self): #Label to show someonen is thinking, makes it more immersive
        name = str(self.state.current_npc).strip() or "Someone"
        return f"{name} is thinking..."

    def _ensure_choice_timer(self):
        if self.choice_timer_started_at is None:
            self.choice_timer_started_at = time.perf_counter()
            return "turn_started"
        return "player_choice_selected"

    def _elapsed_since_choice(self):
        if self.choice_timer_started_at is None:
            return 0.0
        return max(0.0, time.perf_counter() - self.choice_timer_started_at)

    def _show_response_ready(self, timing_meta, errors=None):
        elapsed = float(timing_meta.get("response_ready_seconds", 0.0))
        attempts = 1
        for e in (errors or []):
            if str(e).startswith("json_retry_attempt_"):
                attempts = int(str(e).split("_")[-1])
        print(f"[Response ready in {elapsed:.2f}s | attempts: {attempts}]")

    def _is_fallback_event(self, event):
        if not isinstance(event, dict):
            return False

        event_type = str(event.get("event_type", "")).strip().lower()
        if event_type == "fallback":
            return True

        memory_summary = str(event.get("memory_summary", "")).strip().lower()
        return memory_summary.startswith("fallback response used while speaking with ")

    def _show_resume_context(self):
        print(f"Resumed at {self.state.current_location} with {self.state.current_npc}.")

        last_action = self.state.world_state.get("last_player_action")
        if isinstance(last_action, str) and last_action.strip():
            print(f"Most recent player action: {last_action}")

        narrator = self.state.world_state.get("last_narrator")
        speaker = self.state.world_state.get("last_speaker")
        reply = self.state.world_state.get("last_reply")
        choices = self.state.world_state.get("last_choices")

        if not narrator or not speaker:
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

        if isinstance(choices, list) and choices:
            self.last_choices = _coerce_choice_list(choices)
            type_line("Most recent choices were:")
            for i, choice in enumerate(self.last_choices, start=1):
                type_line(f"  {i}. {choice['text']}")

    def run(self):
        # print("Dynamic mode enabled. LLM is active.")
        if self.resume_mode:
            self._show_resume_context()
            if self.last_choices:
                print("Select a choice to continue.")
                player_choice = self._prompt_for_choice()
                if player_choice is None:
                    return
            else:
                player_choice = {
                    "id": self.state.world_state.get("last_choice_id", "continue_investigation"),
                    "text": self.state.world_state.get(
                        "last_choice_text",
                        self.state.world_state.get("last_player_action", "I continue the investigation."),
                    ),
                    "action_type": "resume",
                }
        else:
            player_choice = dict(self.initial_player_choice)

        while True:
            self.state.turn += 1
            self.state._apply_story_choice_rules(player_choice)
            self.current_player_choice = dict(player_choice)
            closing_turn = self.state.mission_finished()
            timing_meta = {
                "timer_source": self._ensure_choice_timer(),
                "turn_started_elapsed_seconds": round(self._elapsed_since_choice(), 3),
            }

            story_suggestions = suggest_story_choices(
                self.state.world_state,
                self.state.current_npc,
                self.state.current_location,
            )
            forced_choices = forced_story_choices(
                self.state.world_state,
                self.state.current_npc,
                self.state.current_location,
            )
            required_choice_count = 1 if forced_choices else 2
            retrieval_started_at = time.perf_counter()
            memory_summaries, self.last_retrieval = _retrieve_memories(
                player_choice,
                memory_store=self.memory_store,
                current_npc=self.state.current_npc,
                current_location=self.state.current_location,
                world_state=self.state.world_state,
                turn=self.state.turn,
                count_tokens=self._safe_token_count,
                is_fallback_event=self._is_fallback_event,
            )
            timing_meta["retrieval_seconds"] = round(time.perf_counter() - retrieval_started_at, 3)
            arc_state = self.state._current_arc_state()
            prompt_started_at = time.perf_counter()
            prompt_text = _build_prompt(
                prompt_template=self.prompt_template,
                prologue_summary=self.prologue_summary,
                state=self.state.world_state,
                player_choice=player_choice,
                memory_summaries=memory_summaries,
                arc_state=arc_state,
                recent_messages=self.messages,
                turn=self.state.turn,
                known_locations=sorted(set(self.state._known_location_map().values())),
                known_quests=sorted(self.state.world_state.get("active_quests", {}).keys()),
                story_transition=self.state.pending_story_narration or "none",
                required_choice_count=required_choice_count,
                forced_choices=forced_choices,
            )
            timing_meta["prompt_build_seconds"] = round(time.perf_counter() - prompt_started_at, 3)
            self.last_retrieval["prompt_tokens"] = self._safe_token_count(prompt_text)
            timing_meta["prompt_tokens"] = self.last_retrieval["prompt_tokens"]
            timing_meta["memory_tokens"] = self.last_retrieval.get("memory_tokens", 0)

            print(self._thinking_label())
            timing_meta["thinking_label_seconds"] = round(self._elapsed_since_choice(), 3)
            generation_started_at = time.perf_counter()
            try:
                raw_output, parsed_output, errors = _generate_valid_json(
                    self.llm,
                    prompt_text,
                    current_npc=self.state.current_npc,
                    current_location=self.state.current_location,
                    current_player_choice=self.current_player_choice,
                    last_choices=self.last_choices,
                    story_suggestions=story_suggestions,
                    forced_choices=forced_choices,
                    required_choice_count=required_choice_count,
                    world_state=self.state.world_state,
                    arc_state=arc_state,
                )
            except OutputValidationExhausted as exc:
                timing_meta["generation_validation_seconds"] = round(time.perf_counter() - generation_started_at, 3)
                timing_meta["failure_elapsed_seconds"] = round(self._elapsed_since_choice(), 3)
                _log_turn(
                    self.llm,
                    self.state.turn,
                    player_choice,
                    prompt_text,
                    self.last_retrieval,
                    exc.last_raw,
                    None,
                    False,
                    exc.errors,
                    timing_meta=timing_meta,
                )
                _log_failure(
                    self.llm,
                    self.state.turn,
                    player_choice,
                    prompt_text,
                    self.last_retrieval,
                    current_npc=self.state.current_npc,
                    current_location=self.state.current_location,
                    arc_state=arc_state,
                    raw_output=exc.last_raw,
                    errors=exc.errors,
                    attempts=exc.attempts,
                    timing_meta=timing_meta,
                )
                print("Session ended: model could not produce a valid turn.")
                return

            timing_meta["generation_validation_seconds"] = round(time.perf_counter() - generation_started_at, 3)
            parsed_output = self.state._apply_pending_story_narration(parsed_output)

            timing_meta["response_ready_seconds"] = round(self._elapsed_since_choice(), 3)
            if forced_choices:
                parsed_output["choices"] = _coerce_choice_list(forced_choices)[:required_choice_count]
            elif closing_turn:
                parsed_output["choices"] = []

            self.messages.append(
                {
                    "role": "user",
                    "content": f"{player_choice.get('id')}: {player_choice.get('text')}",
                    "npc": self.state.current_npc,
                }
            )
            self._show_response_ready(timing_meta, errors=errors)
            self._show_turn_marker()
            if parsed_output["narrator"]:
                type_line(f"Narrator: {parsed_output['narrator']}")
            if parsed_output["speaker"] and parsed_output["reply"]:
                type_line(f"{parsed_output['speaker']}: {parsed_output['reply']}")
            self.messages.append(
                {
                    "role": "assistant",
                    "content": f"{parsed_output['speaker']}: {parsed_output['reply']}",
                    "npc": parsed_output["speaker"],
                }
            )
            self.last_choices = parsed_output["choices"]

            for i, choice in enumerate(self.last_choices, start=1):
                type_line(f"  {i}. {choice['text']}")

            timing_meta["render_complete_seconds"] = round(self._elapsed_since_choice(), 3)
            _log_turn(
                self.llm,
                self.state.turn,
                player_choice,
                prompt_text,
                self.last_retrieval,
                raw_output,
                parsed_output,
                True,
                errors,
                timing_meta=timing_meta,
            )

            self.state._apply_state_updates(player_choice, parsed_output)
            self.state._persist_turn_memory(player_choice, parsed_output, self.last_retrieval)

            if closing_turn:
                print("Mission complete.")
                self.choice_timer_started_at = None
                return

            if POST_RESPONSE_PAUSE_SECONDS > 0:
                time.sleep(POST_RESPONSE_PAUSE_SECONDS)

            player_choice = self._prompt_for_choice()
            if player_choice is None:
                return
