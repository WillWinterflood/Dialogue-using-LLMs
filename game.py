'''
game.py

Commit 4a runtime:
- hardcoded prologue with scripted choices
- then choice-driven dynamic loop using local LLM JSON outputs
'''

from src.choice_loop import ChoiceLoop
from src.llm_runtime import LocalLLM
from src.prologue import run_prologue


def main():
    llm = LocalLLM()
    try:
        llm.load()
    except Exception as exc:
        print(f"Startup error: {exc}")
        return

    print("Choice loop ready. /quit or /exit to stop.")
    prologue_summary, final_player_action, current_npc, current_location = run_prologue()

    loop = ChoiceLoop(
        llm=llm,
        prologue_summary=prologue_summary,
        initial_player_action=final_player_action,
        current_npc=current_npc,
        current_location=current_location,
    )
    loop.run()


if __name__ == "__main__":
    main()
