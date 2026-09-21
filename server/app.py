"""CrewVoice - browser <-> AssemblyAI Voice Agent bridge.

The API key never leaves this process: the browser talks to us, we talk to
AssemblyAI.  Tool calls are executed here too, against the session's timesheet.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
from contextlib import suppress

import websockets
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .agent import dispatch, session_config
from .mock import MockAgent
from .store import Timesheet

load_dotenv()

AAI_WS_URL = "wss://agents.assemblyai.com/v1/ws"
API_KEY = os.getenv("ASSEMBLYAI_API_KEY", "").strip()
MOCK = os.getenv("CREWVOICE_MOCK", "0") == "1"

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"

app = FastAPI(title="CrewVoice")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

# One timesheet per browser session, kept so /export.csv can find it.
SHEETS: dict[str, Timesheet] = {}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "mock": MOCK, "key_present": bool(API_KEY)}


@app.get("/export.csv")
async def export_csv(session: str = "") -> PlainTextResponse:
    sheet = SHEETS.get(session)
    if sheet is None:
        return PlainTextResponse("no such session\n", status_code=404)
    return PlainTextResponse(
        sheet.to_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="timesheet-{sheet.day}.csv"'},
    )


async def _send(ws: WebSocket, payload: dict) -> None:
    with suppress(RuntimeError, WebSocketDisconnect):
        await ws.send_text(json.dumps(payload))


async def _push_sheet(ws: WebSocket, sheet: Timesheet) -> None:
    await _send(ws, {"type": "sheet", "sheet": sheet.snapshot()})


@app.websocket("/ws")
async def bridge(ws: WebSocket) -> None:
    await ws.accept()
    session_id = os.urandom(6).hex()
    sheet = Timesheet()
    SHEETS[session_id] = sheet
    await _send(ws, {"type": "session", "session_id": session_id, "mock": MOCK})
    await _push_sheet(ws, sheet)

    if MOCK or not API_KEY:
        if not MOCK:
            await _send(ws, {
                "type": "error",
                "message": "ASSEMBLYAI_API_KEY is not set - falling back to the scripted agent.",
            })
        await _run_mock(ws, sheet)
        return

    await _run_live(ws, sheet)


async def _run_live(ws: WebSocket, sheet: Timesheet) -> None:
    headers = {"Authorization": f"Bearer {API_KEY}"}
    try:
        upstream = await websockets.connect(AAI_WS_URL, additional_headers=headers)
    except Exception as exc:  # noqa: BLE001 - surfaced to the operator in the UI
        await _send(ws, {"type": "error", "message": f"cannot reach AssemblyAI: {exc}"})
        await ws.close()
        return

    pending_results: list[dict] = []

    async def browser_to_agent() -> None:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            kind = msg.get("type")
            if kind == "audio":
                await upstream.send(json.dumps({"type": "input.audio", "audio": msg["data"]}))
            elif kind == "stop":
                await upstream.close()
                return

    async def agent_to_browser() -> None:
        async for raw in upstream:
            event = json.loads(raw)
            kind = event.get("type")

            if kind == "transcript.user":
                text = event.get("text", "")
                if text:
                    sheet.last_utterance = text
                await _send(ws, {"type": "user", "text": text})

            elif kind == "transcript.user.delta":
                # partials, so the foreman sees himself being heard
                await _send(ws, {"type": "user_partial", "text": event.get("text", "")})

            elif kind == "transcript.agent":
                await _send(ws, {"type": "agent", "text": event.get("text", "")})

            elif kind == "transcript.agent.delta":
                await _send(ws, {"type": "agent_delta", "text": event.get("delta", "")})

            elif kind == "input.speech.started":
                # barge-in: stop the agent's audio the moment the foreman talks over it
                await _send(ws, {"type": "interrupted"})

            elif kind == "reply.audio":
                await _send(ws, {"type": "audio", "data": event.get("data", "")})

            elif kind == "tool.call":
                name = event.get("name", "")
                args = event.get("arguments") or {}
                result = dispatch(sheet, name, args)
                pending_results.append({
                    "type": "tool.result",
                    "call_id": event.get("call_id"),
                    "result": json.dumps(result, ensure_ascii=False),
                })
                await _send(ws, {"type": "tool", "name": name, "arguments": args, "result": result})
                await _push_sheet(ws, sheet)

            elif kind == "reply.done":
                if event.get("status") == "interrupted":
                    pending_results.clear()
                    await _send(ws, {"type": "interrupted"})
                else:
                    while pending_results:
                        await upstream.send(json.dumps(pending_results.pop(0)))
                await _send(ws, {"type": "turn_done"})

            elif kind == "session.ready":
                await _send(ws, {"type": "ready", "agent_session": event.get("session_id")})

            elif kind == "error":
                await _send(ws, {"type": "error", "message": str(event)})

    await upstream.send(json.dumps(session_config()))

    tasks = [asyncio.create_task(browser_to_agent()), asyncio.create_task(agent_to_browser())]
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            with suppress(WebSocketDisconnect, asyncio.CancelledError):
                task.result()
    except WebSocketDisconnect:
        pass
    finally:
        with suppress(Exception):
            await upstream.close()


async def _run_mock(ws: WebSocket, sheet: Timesheet) -> None:
    """Typed-input agent so the UI, tools and rules can be exercised with no API key."""
    agent = MockAgent(sheet)
    await _send(ws, {"type": "ready", "agent_session": "mock"})
    await _send(ws, {"type": "agent", "text": agent.greeting})
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            if msg.get("type") == "stop":
                return
            if msg.get("type") != "text":
                continue  # mock mode ignores audio frames
            text = (msg.get("text") or "").strip()
            if not text:
                continue
            sheet.last_utterance = text
            await _send(ws, {"type": "user", "text": text})
            for step in agent.turn(text):
                if step["kind"] == "tool":
                    await _send(ws, {
                        "type": "tool",
                        "name": step["name"],
                        "arguments": step["arguments"],
                        "result": step["result"],
                    })
                    await _push_sheet(ws, sheet)
                else:
                    await _send(ws, {"type": "agent", "text": step["text"]})
            await _send(ws, {"type": "turn_done"})
    except WebSocketDisconnect:
        return
