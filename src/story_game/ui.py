'''
src/story_game/ui.py

This is to allow for proper dialogue, a person wouldnt reply straight away... they would this about it. gives some realism and the user can follow along easier
'''
import time

def ellipsis(label, seconds):
    print(label, end="", flush=True)
    for _ in range(seconds):
        time.sleep(2)
        print(".", end="", flush=True)
    print()
