"""Agent configuration and the tool dispatcher."""

from __future__ import annotations

from .store import Timesheet, MAX_HOURS_PER_DAY

SYSTEM_PROMPT = """You take a construction foreman's spoken end-of-day report and turn it into a timesheet.

The foreman is outdoors, holding something, and talking fast. Keep your turns short - one sentence where possible.

Non-negotiable rules:
1. Never invent a name or a number. If you did not clearly hear either, ask.
2. After record_hours you MUST read the name and hours back exactly as the tool returned them, then wait for a yes before calling confirm_entry. A pending entry never reaches payroll.
3. If a tool comes back with ok=false, follow the text in its "say" field. Do not retry with a guessed value.
4. Hours are a working day: anything outside 0 to {max_hours} is a mishearing until the foreman confirms it.
5. If the foreman lists several workers in one breath, handle them one at a time, confirming each.
6. When the foreman says he is finished, call review_day and tell him what is still unconfirmed or never mentioned.

Speak the language the foreman speaks. Say numbers as digits the way a person would."""


GREETING = "Ready for today's hours. Go ahead."

TOOLS = [
    {
        "type": "function",
        "name": "record_hours",
        "description": (
            "Log hours for one crew member. Creates a PENDING entry only - you must read "
            "the result back and call confirm_entry after the foreman agrees."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "worker_name": {
                    "type": "string",
                    "description": "Name exactly as heard. Do not correct it yourself.",
                },
                "hours": {"type": "number", "description": "Hours worked today."},
                "note": {"type": "string", "description": "Optional detail, e.g. 'left early'."},
            },
            "required": ["worker_name", "hours"],
        },
    },
    {
        "type": "function",
        "name": "confirm_entry",
        "description": "Confirm a pending entry after the foreman said yes to the read-back.",
        "parameters": {
            "type": "object",
            "properties": {"entry_id": {"type": "string"}},
            "required": ["entry_id"],
        },
    },
    {
        "type": "function",
        "name": "correct_entry",
        "description": "Change the hours on an existing entry. Sets it back to pending.",
        "parameters": {
            "type": "object",
            "properties": {
                "entry_id": {"type": "string"},
                "hours": {"type": "number"},
            },
            "required": ["entry_id", "hours"],
        },
    },
    {
        "type": "function",
        "name": "mark_absent",
        "description": "Record that a crew member did not work today.",
        "parameters": {
            "type": "object",
            "properties": {
                "worker_name": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["worker_name"],
        },
    },
    {
        "type": "function",
        "name": "review_day",
        "description": "Summarise the day: confirmed, pending, absent and never-mentioned crew.",
        "parameters": {"type": "object", "properties": {}},
    },
]


def session_config(voice: str = "ivy") -> dict:
    return {
        "type": "session.update",
        "session": {
            "system_prompt": SYSTEM_PROMPT.format(max_hours=f"{MAX_HOURS_PER_DAY:g}"),
            "greeting": GREETING,
            "tools": TOOLS,
            "output": {"voice": voice},
        },
    }


def dispatch(sheet: Timesheet, name: str, arguments: dict) -> dict:
    args = arguments or {}
    if name == "record_hours":
        return sheet.record_hours(
            args.get("worker_name", ""), args.get("hours", 0), args.get("note", "")
        )
    if name == "confirm_entry":
        return sheet.confirm_entry(args.get("entry_id", ""))
    if name == "correct_entry":
        return sheet.correct_entry(args.get("entry_id", ""), args.get("hours", 0))
    if name == "mark_absent":
        return sheet.mark_absent(args.get("worker_name", ""), args.get("reason", ""))
    if name == "review_day":
        return sheet.review_day()
    return {"ok": False, "reason": "unknown_tool", "say": f"No tool named {name}."}
