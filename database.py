"""
Database module — stores all bot settings in a JSON file.
"""

import json
import os
import threading
from typing import Any, Dict, List

class Database:
    def __init__(self, path: str = "data.json"):
        self.path = path
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {}
        self._load()

    # ── Internal ──────────────────────────────────────────────────────────────
    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                try:
                    self._data = json.load(f)
                except json.JSONDecodeError:
                    self._data = {}
        else:
            self._data = {}

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    # ── Settings ──────────────────────────────────────────────────────────────
    def get_settings(self, chat_id: int) -> Dict:
        key = str(chat_id)
        with self._lock:
            return self._data.get(key, {})

    def save_settings(self, chat_id: int, settings: Dict):
        key = str(chat_id)
        with self._lock:
            self._data[key] = settings
            self._save()

    def delete_settings(self, chat_id: int):
        key = str(chat_id)
        with self._lock:
            if key in self._data:
                del self._data[key]
                self._save()

    # ── Admin → Chat Mapping ──────────────────────────────────────────────────
    def get_linked_chats(self, user_id: int) -> List[int]:
        """Return all chat IDs where this user is an admin."""
        linked = []
        with self._lock:
            for chat_id_str, settings in self._data.items():
                if user_id in settings.get("admins", []):
                    linked.append(int(chat_id_str))
        return linked

    # ── Utilities ─────────────────────────────────────────────────────────────
    def all_chats(self) -> List[int]:
        with self._lock:
            return [int(k) for k in self._data.keys()]
