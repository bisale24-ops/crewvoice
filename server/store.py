"""Timesheet state for one voice session.

The rule the whole product rests on: an entry reaches the payroll export only
after the agent read the numbers back and the foreman said yes.  Everything
else sits in `pending` and is visible as such.
"""

from __future__ import annotations

import csv
import io
import itertools
import time
from dataclasses import dataclass, field, asdict
from difflib import get_close_matches

# A real deployment pulls this from CrewSheet.  Hard-coded roster keeps the
# demo self-contained and, more importantly, gives the agent something to
# check heard names against.
DEFAULT_ROSTER = [
    "Azamat Sultanov",
    "Marat Beishenov",
    "Bekzat Orozov",
    "Daniyar Ismailov",
    "Nurlan Toktogulov",
    "Sergey Kim",
]

MAX_HOURS_PER_DAY = 16.0


@dataclass
class Entry:
    id: str
    worker: str
    hours: float
    date: str
    status: str                      # pending | confirmed | absent
    note: str = ""
    said_at: float = field(default_factory=time.time)
    heard: str = ""                  # the utterance this entry came from
    heard_name: str = ""             # what ASR produced before roster matching

    def as_dict(self) -> dict:
        return asdict(self)


class Timesheet:
    def __init__(self, roster: list[str] | None = None, day: str | None = None):
        self.roster = list(roster or DEFAULT_ROSTER)
        self.day = day or time.strftime("%Y-%m-%d")
        self.entries: dict[str, Entry] = {}
        self._ids = itertools.count(1)
        self.last_utterance = ""

    # ---------- helpers ----------

    def _next_id(self) -> str:
        return f"e{next(self._ids)}"

    def match_worker(self, spoken: str) -> tuple[str | None, list[str]]:
        """Map a heard name onto the roster.

        Returns (exact_match, candidates).  ASR mangles names constantly, and a
        wrong name on a timesheet pays the wrong person, so an ambiguous match
        is never resolved silently - it goes back to the agent as a question.
        """
        spoken = (spoken or "").strip()
        if not spoken:
            return None, []
        lowered = {name.lower(): name for name in self.roster}

        if spoken.lower() in lowered:
            return lowered[spoken.lower()], []

        first_names = {name.split()[0].lower(): name for name in self.roster}
        if spoken.lower() in first_names:
            return first_names[spoken.lower()], []

        # "Bek" for "Bekzat" - a prefix of a first name, long enough to mean something.
        if len(spoken) >= 3:
            prefixed = [
                name for first, name in first_names.items()
                if first.startswith(spoken.lower())
            ]
            if len(prefixed) == 1:
                return prefixed[0], []
            if prefixed:
                return None, prefixed

        pool = list(lowered) + list(first_names)
        hits = get_close_matches(spoken.lower(), pool, n=3, cutoff=0.72)
        resolved, seen = [], set()
        for hit in hits:
            name = lowered.get(hit) or first_names.get(hit)
            if name and name not in seen:
                seen.add(name)
                resolved.append(name)
        if len(resolved) == 1:
            return resolved[0], []
        return None, resolved

    def hours_for(self, worker: str) -> float:
        return sum(
            e.hours for e in self.entries.values()
            if e.worker == worker and e.status in ("pending", "confirmed")
        )

    # ---------- tool bodies ----------

    def record_hours(self, worker_name: str, hours: float, note: str = "") -> dict:
        worker, candidates = self.match_worker(worker_name)
        if worker is None:
            return {
                "ok": False,
                "reason": "unknown_worker",
                "heard": worker_name,
                "candidates": candidates or self.roster,
                "say": (
                    f"I could not match '{worker_name}' to the crew list. "
                    "Ask which of the listed names it is - do not guess."
                ),
            }

        try:
            hours = float(hours)
        except (TypeError, ValueError):
            return {"ok": False, "reason": "bad_hours", "say": "Ask for the hours again as a number."}

        if hours <= 0 or hours > MAX_HOURS_PER_DAY:
            return {
                "ok": False,
                "reason": "out_of_range",
                "say": (
                    f"{hours} hours is outside 0-{MAX_HOURS_PER_DAY:g} for one day. "
                    "Read it back and ask the foreman to repeat it."
                ),
            }

        already = self.hours_for(worker)
        if already + hours > MAX_HOURS_PER_DAY:
            return {
                "ok": False,
                "reason": "day_total_exceeded",
                "existing_hours": already,
                "say": (
                    f"{worker} already has {already:g} hours today; adding {hours:g} "
                    "goes over a full day. Ask whether this replaces the earlier entry."
                ),
            }

        entry = Entry(
            id=self._next_id(),
            worker=worker,
            hours=hours,
            date=self.day,
            status="pending",
            note=note or "",
            heard=self.last_utterance,
            heard_name=worker_name,
        )
        self.entries[entry.id] = entry
        return {
            "ok": True,
            "entry_id": entry.id,
            "status": "pending",
            "say": (
                f"Read back exactly this and wait for a yes: {worker}, {hours:g} hours. "
                "Nothing is saved to payroll until you call confirm_entry."
            ),
            "entry": entry.as_dict(),
        }

    def confirm_entry(self, entry_id: str) -> dict:
        entry = self.entries.get(entry_id)
        if entry is None:
            return {"ok": False, "reason": "no_such_entry", "say": "That entry id does not exist."}
        if entry.status == "confirmed":
            return {"ok": True, "entry_id": entry_id, "status": "confirmed", "say": "Already confirmed."}
        entry.status = "confirmed"
        return {
            "ok": True,
            "entry_id": entry_id,
            "status": "confirmed",
            "say": f"{entry.worker}, {entry.hours:g} hours is now on the timesheet.",
            "entry": entry.as_dict(),
        }

    def correct_entry(self, entry_id: str, hours: float) -> dict:
        entry = self.entries.get(entry_id)
        if entry is None:
            return {"ok": False, "reason": "no_such_entry", "say": "That entry id does not exist."}
        try:
            hours = float(hours)
        except (TypeError, ValueError):
            return {"ok": False, "reason": "bad_hours", "say": "Ask for the corrected hours again."}
        if hours <= 0 or hours > MAX_HOURS_PER_DAY:
            return {"ok": False, "reason": "out_of_range", "say": "That is outside a plausible working day."}
        entry.hours = hours
        entry.status = "pending"
        entry.heard = self.last_utterance
        return {
            "ok": True,
            "entry_id": entry_id,
            "status": "pending",
            "say": f"Corrected to {hours:g} hours - read it back and confirm again.",
            "entry": entry.as_dict(),
        }

    def mark_absent(self, worker_name: str, reason: str = "") -> dict:
        worker, candidates = self.match_worker(worker_name)
        if worker is None:
            return {
                "ok": False,
                "reason": "unknown_worker",
                "candidates": candidates or self.roster,
                "say": f"'{worker_name}' is not on the crew list. Ask which name it is.",
            }
        entry = Entry(
            id=self._next_id(),
            worker=worker,
            hours=0.0,
            date=self.day,
            status="absent",
            note=reason or "",
            heard=self.last_utterance,
            heard_name=worker_name,
        )
        self.entries[entry.id] = entry
        return {
            "ok": True,
            "entry_id": entry.id,
            "status": "absent",
            "say": f"Marked {worker} absent" + (f" - {reason}." if reason else "."),
            "entry": entry.as_dict(),
        }

    def review_day(self) -> dict:
        confirmed = [e for e in self.entries.values() if e.status == "confirmed"]
        pending = [e for e in self.entries.values() if e.status == "pending"]
        absent = [e for e in self.entries.values() if e.status == "absent"]
        missing = [
            name for name in self.roster
            if not any(e.worker == name for e in self.entries.values())
        ]
        return {
            "ok": True,
            "date": self.day,
            "confirmed": [e.as_dict() for e in confirmed],
            "pending": [e.as_dict() for e in pending],
            "absent": [e.as_dict() for e in absent],
            "not_mentioned": missing,
            "total_confirmed_hours": sum(e.hours for e in confirmed),
            "say": (
                f"{len(confirmed)} confirmed, {len(pending)} waiting for a yes, "
                f"{len(absent)} absent, {len(missing)} never mentioned."
            ),
        }

    # ---------- export ----------

    def snapshot(self) -> dict:
        return {
            "date": self.day,
            "roster": self.roster,
            "entries": [e.as_dict() for e in self.entries.values()],
            "total_confirmed_hours": sum(
                e.hours for e in self.entries.values() if e.status == "confirmed"
            ),
        }

    def to_csv(self) -> str:
        """Only confirmed rows leave the building."""
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["date", "worker", "hours", "note", "heard_as", "source_utterance"])
        for e in self.entries.values():
            if e.status != "confirmed":
                continue
            writer.writerow([e.date, e.worker, f"{e.hours:g}", e.note, e.heard_name, e.heard])
        return buf.getvalue()
