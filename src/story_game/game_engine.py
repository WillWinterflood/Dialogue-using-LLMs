'''
src/story_game/game_engine.py

Runs the game loop and handles the scripted choices and the player input + commands
This also prints the narration/dialogue/ choices
Essentially is connecting each part and eventually will include some llm things aswell

'''
from story_game.arc import apply_story_director
from story_game.models import DialogueEntry
from story_game.story_data import build_initial_state
from story_game.ui import ellipsis


class StoryGame:
    def __init__(self):
        self.state = build_initial_state()

    #Start the game and show the intro and allow for user input until interupted (ctrl C)
    def run(self):
        self._print_intro()
        self._run_scripted_choices()
        print("\nBaseline: no LLM implemented yet****")
        print("Type /help for commands.\n")

        while True:
            try:
                user_text = input("You > ").strip()
            except KeyboardInterrupt:
                print("\nSession interrupted.")
                break

            if not user_text:
                continue

            if user_text.startswith("/"):
                if self._handle_command(user_text):
                    break
                continue

            self._handle_player_turn(user_text)

    def _print_intro(self):
        print("### PROLOGUE (HARDCODED) ###")
        for line in self.state.history:
            print(f"{line.speaker}: {line.text}")

    #This is the start scripted choices before the llm starts
    def _run_scripted_choices(self):
        print("\n### SCRIPTED CHOICES ###")

        c1 = self._prompt_choice(
            "How do you answer Mara?",
            ["I'm in. Tell me where to start.", "Why pick me for this?"],
        )

        if c1 == 1:
            self._append("Alex", "I'm in. Tell me where to start.")
            ellipsis("Mara is thinking", 2)
            self._append("Mara", "Good. Keep your head down and your ears open.")
        else:
            self._append("Alex", "Why pick me for this?")
            ellipsis("Mara is thinking", 2)
            self._append("Mara", "Because you still care what this town becomes. That's rare.")

        c2 = self._prompt_choice(
            "What is your first move?",
            ["Go straight to Eli at the Market Gate.", "Check the library shipping records first."],
        )

        if c2 == 1:
            self._append("Alex", "I'll go to the Market Gate and find Eli.")
            ellipsis("Mara is thinking", 2)
            self._append("Mara", "Ask short questions. Eli lies when people ramble.")
            self.state.active_npc = "eli"
            self.state.quests["echo_shard"].objective = "Talk to Eli at the Market Gate about the missing shipment."
        else:
            self._append("Alex", "I'll check your shipping records first.")
            ellipsis("Mara is thinking", 2)
            self._append("Mara", "Fine. Find ledger 7C, then go to Eli with facts in hand.")
            self.state.quests["echo_shard"].objective = "Inspect ledger 7C in the Old Library, then question Eli."
        #Now this is when the LLM should take over, going to remove this in the future...
        self.state.phase = "dynamic"
        print("Narrator: The scripted prologue ends. From here, the baseline loop reacts to input.")

    def _append(self, speaker, text):
        self.state.history.append(DialogueEntry(speaker=speaker, text=text, mode="scripted"))
        print(f"{speaker}: {text}")

    #Choosing one of the 2 choices
    def _prompt_choice(self, prompt, options):
        print(prompt)
        for i, opt in enumerate(options, start=1):
            print(f"  {i}) {opt}")
        while True:
            raw = input("Choice > ").strip()
            if raw in {"1", "2"}:
                return int(raw)
            print("Enter 1 or 2.")

    #The finish (needs improving later)
    def _handle_player_turn(self, user_text):
        self.state.history.append(DialogueEntry(self.state.player.name, user_text, mode="dynamic", tags=["player_input"]))
        apply_story_director(self.state, user_text)

        if self.state.story_act == "finished":
            print("Narrator: The storm thins to a mist as the case closes.")
            print("Mara: It's done.")
            return

        print("Narrator: Baseline mode recorded your input.")
        print(f"Active act: {self.state.story_act}. Current objective: {self.state.quests['echo_shard'].objective}")
