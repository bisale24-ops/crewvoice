"""A scripted stand-in for the Voice Agent, used when no API key is present.

It is deliberately dumb - regexes, not an LLM - because its only job is to
drive the same tool calls the real agent drives, so the timesheet rules and the
UI can be tested offline.
"""

from __future__ import annotations

import re

from .agent import dispatch
from .store import Timesheet

NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "half": 0.5,
    # Russian, because the crew this is built for speaks it
    "ноль": 0, "один": 1, "два": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6,
    "семь": 7, "восемь": 8, "девять": 9, "десять": 10, "одиннадцать": 11,
    "двенадцать": 12, "двадцать": 20,
}

YES = {"yes", "yeah", "yep", "correct", "right", "da", "да", "ага", "верно"}
NO = {"no", "nope", "wrong", "нет", "не"}


def _to_hours(token: str) -> float | None:
    token = token.lower().strip()
    if token in NUMBER_WORDS:
        return float(NUMBER_WORDS[token])
    try:
        return float(token.replace(",", "."))
    except ValueError:
        return None


class MockAgent:
    greeting = "Ready for today's hours. Go ahead. (scripted agent - no API key loaded)"

    def __init__(self, sheet: Timesheet):
        self.sheet = sheet
        self.awaiting: str | None = None      # entry id waiting for a yes

    def turn(self, text: str) -> list[dict]:
        out: list[dict] = []
        lowered = text.lower().strip(" .!?")

        if self.awaiting and lowered in YES:
            entry_id, self.awaiting = self.awaiting, None
            out.append(self._call("confirm_entry", {"entry_id": entry_id}))
            out.append({"kind": "say", "text": out[-1]["result"]["say"]})
            return out

        if self.awaiting and lowered in NO:
            self.awaiting = None
            out.append({"kind": "say", "text": "Dropped it. Say the name and hours again."})
            return out

        if lowered in {"done", "finished", "that's it", "review", "всё", "все"}:
            out.append(self._call("review_day", {}))
            out.append({"kind": "say", "text": out[-1]["result"]["say"]})
            return out

        absent = re.match(r"(.+?)\s+(?:was\s+)?(?:absent|off|did not work|didn't work|не вышел)\b(.*)", text, re.I)
        if absent:
            out.append(self._call("mark_absent", {
                "worker_name": absent.group(1).strip(),
                "reason": absent.group(2).strip(" ,.-"),
            }))
            out.append({"kind": "say", "text": out[-1]["result"]["say"]})
            return out

        hours = re.match(r"(.+?)\s+([\w.,]+)\s*(?:hours?|hrs?|часов|часа|ч)\b(.*)", text, re.I)
        if hours:
            value = _to_hours(hours.group(2))
            if value is None:
                out.append({"kind": "say", "text": "I did not catch the number of hours."})
                return out
            out.append(self._call("record_hours", {
                "worker_name": hours.group(1).strip(),
                "hours": value,
                "note": hours.group(3).strip(" ,.-"),
            }))
            result = out[-1]["result"]
            if result.get("ok"):
                self.awaiting = result["entry_id"]
                entry = result["entry"]
                out.append({
                    "kind": "say",
                    "text": f"{entry['worker']}, {entry['hours']:g} hours - is that right?",
                })
            else:
                out.append({"kind": "say", "text": result["say"]})
            return out

        out.append({
            "kind": "say",
            "text": "Say it as a name and hours, for example 'Azamat nine hours'. Say 'done' to review.",
        })
        return out

    def _call(self, name: str, arguments: dict) -> dict:
        return {
            "kind": "tool",
            "name": name,
            "arguments": arguments,
            "result": dispatch(self.sheet, name, arguments),
        }
