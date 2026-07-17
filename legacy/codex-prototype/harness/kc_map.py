"""R6: Knowledge Concept (KC) and Question numbering with persistence.

KC mapping v1 uses an explicit kc_hint (a short concept label produced by the
intervention generator); identical hints share a KC, identical normalized
question text shares a Question number. Embedding-similarity mapping can
replace hint equality later without changing the interface.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class QuestionRef:
    kc_id: int
    q_id: int


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


class KCStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            data = {"kcs": {}, "questions": {}}
        self._kcs: dict[str, int] = data["kcs"]           # hint -> kc_id
        self._questions: dict[str, list[int]] = data["questions"]  # norm text -> [kc_id, q_id]

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"kcs": self._kcs, "questions": self._questions}, ensure_ascii=False),
            encoding="utf-8",
        )

    def assign(self, question_text: str, *, kc_hint: str) -> QuestionRef:
        """Return a stable (kc_id, q_id) for this question, creating ids as needed."""
        norm = _normalize(question_text)
        hint = _normalize(kc_hint)
        if norm in self._questions:
            kc_id, q_id = self._questions[norm]
            return QuestionRef(kc_id, q_id)
        if hint not in self._kcs:
            self._kcs[hint] = len(self._kcs) + 1
        kc_id = self._kcs[hint]
        q_id = len(self._questions) + 1
        self._questions[norm] = [kc_id, q_id]
        self._save()
        return QuestionRef(kc_id, q_id)

    def record_outcome(self, seq_path: Path | str, *, user_id: str, q: QuestionRef, correct: int) -> None:
        """Append one graded outcome to the KT sequence CSV (header on create)."""
        seq_path = Path(seq_path)
        seq_path.parent.mkdir(parents=True, exist_ok=True)
        new = not seq_path.exists()
        with seq_path.open("a", encoding="utf-8") as f:
            if new:
                f.write("user_id,kc_id,q_id,correct,ts\n")
            f.write(f"{user_id},{q.kc_id},{q.q_id},{int(correct)},{time.time()}\n")
