# CrewVoice

A foreman finishes the day, says who worked how long, and walks away. Payroll
gets a timesheet where every row can be traced back to the words it came from.

Built on the **AssemblyAI Voice Agent API** for the AssemblyAI Voice Agent
Hackathon (Sep 1-30, 2026).

## The one rule

A number the agent heard is not a number the agent may pay out. `record_hours`
only ever creates a **pending** row; the agent has to read the name and hours
back, hear a yes, and call `confirm_entry`. `/export.csv` contains confirmed
rows only - so a mishearing that nobody confirmed cannot reach payroll, and the
UI shows exactly what is still waiting.

Three more refusals live in the tools, not in the prompt, so the model cannot
talk its way past them:

- a name that does not match the crew list comes back as a question, never a guess;
- hours outside 0-16 for one day are rejected and re-asked;
- a second entry that pushes someone over a full day asks whether it replaces the first.

Every confirmed row carries `heard_as` (what speech recognition produced) and
`source_utterance` (the sentence it came from), so a disputed hour is settled by
looking at the record instead of arguing.

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # put your AssemblyAI key in it
uvicorn server.app:app --reload --port 3000
```

Open http://localhost:3000 and press **Start talking**.

Without a key the app still runs: it falls back to a scripted agent driven by a
text box, which exercises the same tools and the same rules (`CREWVOICE_MOCK=1`
forces it). Try: `Azamat nine hours` → `yes` → `Sergey 20 hours` → `done`.

## Names and languages

A crew list says `José Ramírez`. Speech recognition writes `Jose`. The foreman
says `Ramirez`, or just `Jose`, or answers in Spanish. Names are folded to bare
lowercase ASCII on both sides before they are compared - accents dropped,
first names, surnames and short forms all indexed - so the same person is found
however the name arrived. Anything that still does not resolve comes back as a
question with the candidates, because paying the wrong Jose is worse than
asking.

The agent answers in the language it was spoken to; AssemblyAI's model handles
the switch mid-sentence, which is how bilingual sites actually talk.

## Deploy

`render.yaml` in the repo root is a Render blueprint: New → Blueprint → pick this
repo, then set `ASSEMBLYAI_API_KEY` in the dashboard. The free instance sleeps
after ~15 minutes, so open the URL once before showing it to anyone.

## How it fits together

```
browser mic ──PCM16/24kHz──▶ FastAPI bridge ──▶ wss://agents.assemblyai.com/v1/ws
    ▲                             │  tool.call
    └────── agent audio ──────────┴──▶ timesheet rules ──▶ /export.csv
```

The API key stays on the server; the browser never sees it.

MIT licensed.
