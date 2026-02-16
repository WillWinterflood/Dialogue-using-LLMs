'''
src/models.py

Defining the core data being used in the game
'''

from datetime import datetime

#Class for everyone (both user and npcs)
class Character:
    def __init__(self, name, role, bio, traits=None, speaking_style=""):
        self.name = name
        self.role = role
        self.bio = bio
        self.traits = traits or []
        self.speaking_style = speaking_style

class NPC(Character):
    #There is more to NPCs as there must be a location and some trust (for emotions)
    def __init__(
        self,
        name,
        role,
        bio,
        traits=None,
        speaking_style="",
        location="",
        trust_level=0,
    ):

        super().__init__(name, role, bio, traits=traits, speaking_style=speaking_style)       
        # NPC-specific state.
        self.location = location
        self.trust_level = trust_level

class Quest:
    def __init__(
        self,
        quest_id,
        title,
        description,
        giver,
        status="not started",
        objective="",
    ):
        self.quest_id = quest_id
        self.title =title
        self.description = description
        self.giver = giver
        self.status = status
        self.objective = objective

class DialogueEntry:
    def __init__(self, speaker, text, timestamp=None, mode="scripted", tags=None):
        self.speaker = speaker
        self.text = text 
        self.timestamp = timestamp
        self.mode = mode
        self.tags = tags or []

class GameState:
    def __init__(self,
    player,
    npcs,
    quests,
    active_npc, #Who is the conversation focused on 
    phase="intro", #it isnt dynamic yet (no LLM)
    history=None,
    story_act="beginning", 
    story_goal="Recover the missing Echo Shard and decide what to report",
    story_turn=0, #How many times the LLM has had a turn
    max_story_turns=18, #Forcing an ending right now
    met_eli=False,
    beat_found_clue=False,
    beat_truth_decision=False, #Whether the user tells the truth or not
    ending_summary="",
    ):
        # Core entities.
        self.player = player
        self.npcs = npcs
        self.quests = quests
        self.active_npc = active_npc
        self.phase = phase
        self.history = history or []
        self.story_act = story_act
        self.story_goal = story_goal
        self.story_turn = story_turn
        self.max_story_turns = max_story_turns
        self.met_eli = met_eli
        self.beat_found_clue = beat_found_clue
        self.beat_truth_decision = beat_truth_decision
        self.ending_summary = ending_summary


    def quest_view(self):
        # Build a printable quest summary for CLI commands.
        lines = []
        for q in self.quests.values():
            lines.append(f"[{q.status}] {q.title} - {q.objective or q.description}")
        return "\n".join(lines)