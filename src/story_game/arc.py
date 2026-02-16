'''
src/story_game/arc.py

Ensuring that there is a beginning, middle and end.., Need to make it clearer to the llm in future
this is very basic right now 
'''

def apply_story_director(state, player_text):
    text = player_text.lower()
    state.story_turn += 1

    if state.story_act == "beginning":
        if "eli" in text or "market gate" in text:
            state.met_eli = True
            state.story_act ="middle"
    
    elif state.story_act == "middle":
        if "ledger" in text or "clue" in text or "signature" in text:
            state.beat_found_clue = True
            state.story_act = "end"
    
    elif state.story_act == "end":
        if "truth" in text or "report" in text or "lie" in text:
            state.beat_truth_decision = True
            state.story_act = "finished"
            state.ending_summary = "Alex resolved the Echo Shard case."
            q = state.quests.get("echo_shard")
            if q:
                q.status = "completed"
                q.objective = "Case closed."