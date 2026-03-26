'''
src/config.py

Keeping all the important numbers in one place
'''

from pathlib import Path

PROMPT_PATH = Path("prompts/prompt_v1.txt")
LOG_PATH = Path("dialogue_log.jsonl")
FAILURE_LOG_PATH = Path("failure_log.jsonl")

POST_RESPONSE_PAUSE_SECONDS = 0.2
PLAYER_CHOICE_SPEAK_SECONDS = 0.2

MAX_JSON_RETRY_ATTEMPTS = 4

MIN_LLM_CHOICES = 1
MAX_LLM_CHOICES = 2

MEMORY_RECENT_TURNS = 8
MEMORY_NPC_TURNS = 20
MEMORY_TOP_K = 2
MEMORY_TOKEN_BUDGET = 200
PROMPT_RECENT_MESSAGES = 6

VALID_TIME_OF_DAY = {"dawn", "morning", "noon", "afternoon", "evening", "night"}
ALLOWED_QUEST_STATUS = {"not_started", "active", "completed", "failed"}
ALLOWED_ACTION_TYPES = {"ask", "investigate", "travel", "accuse", "reassure", "threaten", "trade", "exit", "resume"}
ALLOWED_EVENT_TYPES = {"dialogue", "clue", "promise", "debt", "threat", "travel", "quest", "fallback", "handoff", "prologue"}
ALLOWED_STATE_UPDATE_KEYS = {"time_of_day", "day"}

GENERIC_LOOP_MARKERS = (
    "anything else",
    "suspicious activity",
    "what else",
    "tell me more",
)

STOPWORDS = { #Low value words that gets ignored during text matching
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
