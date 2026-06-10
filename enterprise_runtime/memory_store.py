from __future__ import annotations

import json
from typing import Dict, List

from enterprise_runtime.config import MEMORY_ROOT
from enterprise_runtime.utils import now_str, sanitize_id


class MemoryStore:
    def __init__(self, tenant_id: str, user_id: str):
        self.path = MEMORY_ROOT / tenant_id / f"{sanitize_id(user_id, 'guest')}.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load_raw(self) -> List[Dict[str, str]]:
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text(encoding="utf-8")).get("history", [])
        except Exception:
            return []

    def save(self, history: List[Dict[str, str]]) -> None:
        self.path.write_text(
            json.dumps({"history": history[-60:]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def append(self, role: str, content: str) -> None:
        history = self.load_raw()
        history.append({"role": role, "content": content.strip(), "ts": now_str()})
        self.save(history)

    def load(self, turns: int) -> str:
        history = self.load_raw()
        if not history:
            return "No conversation history is available."
        items = history[-turns * 2 :]
        return "\n".join(f"- {h['role']}: {h['content']}" for h in items)

    def reset(self) -> None:
        self.save([])
