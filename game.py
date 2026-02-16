from story_game.game_engine import StoryGame

def main():
    try:
        game = StoryGame()
        game.run()
    except Exception as exc:
        print(f"Startup error: {exc}")

if __name__ == "__main__":
    main()