"""Atomic JSON I/O for state/ files.

Two state files live at repo root:
  state/topic-queue.json — { "current_week": "...", "topics": [...] }
  state/history.json     — { "runs": [...] }

Both can be touched by overlapping workflows (Thu topic-gen + Mon auto-approve
+ Mon/Wed/Fri publish), so reads/writes go through exclusive file locks and
atomic rename to prevent torn writes.
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = REPO_ROOT / "state"
TOPIC_QUEUE_FILE = STATE_DIR / "topic-queue.json"
HISTORY_FILE = STATE_DIR / "history.json"

LOCK_TIMEOUT_SECONDS = 30


class StateLockTimeout(RuntimeError):
    """Raised when we can't acquire an exclusive lock within LOCK_TIMEOUT_SECONDS."""


@contextlib.contextmanager
def _locked(path: Path) -> Iterator[int]:
    """Acquire an exclusive flock on a sidecar .lock file, blocking up to LOCK_TIMEOUT_SECONDS."""
    lock_path = path.with_suffix(path.suffix + ".lock")
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        import signal

        def _timeout_handler(signum, frame):
            raise StateLockTimeout(f"could not acquire lock on {lock_path} in {LOCK_TIMEOUT_SECONDS}s")

        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(LOCK_TIMEOUT_SECONDS)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
        yield fd
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _atomic_write_json(path: Path, payload: Any) -> None:
    """Write JSON to a temp file in the same dir, then rename. Survives crashes mid-write."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    # Same dir so rename is atomic (cross-fs renames are not).
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_path)
        raise


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    with open(path, "r", encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        return default
    return json.loads(text)


# ---------- topic-queue ----------

@dataclass
class TopicQueue:
    current_week: Optional[str] = None
    topics: list = field(default_factory=list)
    slack: Optional[dict] = None
    approval: Optional[dict] = None

    @classmethod
    def from_dict(cls, d: dict) -> "TopicQueue":
        return cls(
            current_week=d.get("current_week"),
            topics=list(d.get("topics", [])),
            slack=d.get("slack"),
            approval=d.get("approval"),
        )

    def to_dict(self) -> dict:
        out: dict = {"current_week": self.current_week, "topics": list(self.topics)}
        if self.slack is not None:
            out["slack"] = self.slack
        if self.approval is not None:
            out["approval"] = self.approval
        return out


def read_topic_queue() -> TopicQueue:
    with _locked(TOPIC_QUEUE_FILE):
        data = _read_json(TOPIC_QUEUE_FILE, {"current_week": None, "topics": []})
    return TopicQueue.from_dict(data)


def write_topic_queue(queue: TopicQueue) -> None:
    with _locked(TOPIC_QUEUE_FILE):
        _atomic_write_json(TOPIC_QUEUE_FILE, queue.to_dict())


@contextlib.contextmanager
def topic_queue_transaction() -> Iterator[TopicQueue]:
    """Acquire the lock once; read, yield, write back. Use for read-modify-write."""
    with _locked(TOPIC_QUEUE_FILE):
        data = _read_json(TOPIC_QUEUE_FILE, {"current_week": None, "topics": []})
        queue = TopicQueue.from_dict(data)
        yield queue
        _atomic_write_json(TOPIC_QUEUE_FILE, queue.to_dict())


# ---------- history ----------

def read_history() -> dict:
    with _locked(HISTORY_FILE):
        return _read_json(HISTORY_FILE, {"runs": []})


def append_history_run(run: dict) -> None:
    """Append a single run record. Preserves any other top-level keys."""
    with _locked(HISTORY_FILE):
        data = _read_json(HISTORY_FILE, {"runs": []})
        data.setdefault("runs", []).append(run)
        _atomic_write_json(HISTORY_FILE, data)


@contextlib.contextmanager
def history_transaction() -> Iterator[dict]:
    """Same pattern as topic_queue_transaction but for history.json."""
    with _locked(HISTORY_FILE):
        data = _read_json(HISTORY_FILE, {"runs": []})
        yield data
        _atomic_write_json(HISTORY_FILE, data)


if __name__ == "__main__":
    # Sanity test: round-trip both files, verify locking doesn't deadlock from same process.
    print("=== topic-queue round-trip ===")
    q = read_topic_queue()
    print(f"initial: current_week={q.current_week!r}, topics={len(q.topics)}")

    with topic_queue_transaction() as queue:
        queue.current_week = "2026-05-21-test"
        queue.topics = [{"id": "t1", "title": "Sanity test topic"}]
    print("wrote test data")

    q2 = read_topic_queue()
    print(f"reread:  current_week={q2.current_week!r}, topics={len(q2.topics)}")
    assert q2.current_week == "2026-05-21-test"
    assert q2.topics[0]["title"] == "Sanity test topic"

    # Reset to empty
    with topic_queue_transaction() as queue:
        queue.current_week = None
        queue.topics = []
    print("reset to empty")

    print("\n=== history round-trip ===")
    h = read_history()
    initial_count = len(h["runs"])
    print(f"initial runs: {initial_count}")

    append_history_run({"id": "sanity-test", "ts": "2026-05-21T17:00:00Z", "result": "ok"})
    h2 = read_history()
    print(f"after append: {len(h2['runs'])}")
    assert len(h2["runs"]) == initial_count + 1

    # Roll back the test entry
    with history_transaction() as data:
        data["runs"] = [r for r in data["runs"] if r.get("id") != "sanity-test"]
    h3 = read_history()
    print(f"after rollback: {len(h3['runs'])}")
    assert len(h3["runs"]) == initial_count

    print("\nALL ASSERTIONS PASSED")
