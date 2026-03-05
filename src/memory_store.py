"""
src/memory_store.py

Simple memory journaling
Each turn is appended to JSONL files so memory persists between sessions
"""

import json
from pathlib import Path

class MemoryStore:
    def __init__(self, root="data/memory"): #Folder where the memory files are
        self.root = Path(root)

    def _append_jsonl(self, path, row): #Appending a row in a jsonl file and then creating the file
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    def _read_jsonl(self, path, n): #Reading the last n valid lines from the jsonl file, returning the eldest first
        if not path.exists():
            return []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return []
        rows = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
            if len(rows) == n:
                break
        return list(reversed(rows))

    def append_turn(self, row): 
        self._append_jsonl(self.root / "turns.jsonl", row)

    def append_npc_memory(self, npc_name, row):
        if not npc_name:
            return
        safe_name = str(npc_name).strip().lower().replace(" ", "_")
        self._append_jsonl(self.root / f"{safe_name}.jsonl", row)

    def load_last_turn(self): #loading the last save
        path = self.root / "turns.jsonl"
        if not path.exists():
            return None
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            if not lines:
                return None
            return json.loads(lines[-1])
        except Exception:
            return None

    def load_recent_turns(self, n=5):
        return self._read_jsonl(self.root / "turns.jsonl", n)

    def load_npc_turns(self, npc_name, n=3):
        if not npc_name: 
            return []
        safe_name = str(npc_name).strip().lower().replace(" ", "_")
        return self._read_jsonl(self.root / f"{safe_name}.jsonl", n)

    def reset(self): #Starting fresh and removing all memory files
        if not self.root.exists(): 
            return
        for path in self.root.glob("*.jsonl"):
            path.unlink(missing_ok=True)
