# 🚨 IncidentIQ — an incident-response agent that learns with Hindsight

Engineers re-solve the same outages because the fix lives in a forgotten ticket or Slack thread.
IncidentIQ **retains** every resolved incident (symptoms, root cause, working fix, failed attempts)
in [Hindsight](https://github.com/vectorize-io/hindsight) and **recalls** it when a similar incident
shows up, so the recommendation gets sharper every time the team resolves something.

## Problem statement
When production breaks, engineers waste time re-discovering how a near-identical incident was fixed
weeks ago. A stateless chatbot can't help with this — it forgets the moment the chat ends. This
project makes memory the core of the agent, not a bolt-on feature.

## Solution
An agent that, for every new incident:
1. **Recalls** similar past incidents from Hindsight (symptom, root cause, fix, what failed).
2. **Analyzes** the new incident together with those memories using an LLM (Groq).
3. Shows a recommendation, and — for comparison — what a memoryless agent would have said instead.

Once the engineer resolves the incident, the outcome is **retained** back into Hindsight, so the next
similar incident benefits from it.

## Architecture
```
Engineer → Streamlit UI → Agent
                             │
                    Hindsight recall (past incidents)
                             │
                        Groq LLM (analysis)
                             │
              Recommendation shown side-by-side:
              "without memory" vs "with Hindsight memory"
                             │
        Engineer confirms root cause + fix + what failed
                             │
                    Hindsight retain (new memory)
                             │
                  Agent is measurably smarter next time
```

## Where Hindsight is used
- `core/hindsight_memory.py` — `Memory.retain()` and `Memory.recall()` / `recall_parsed()`. Falls back
  to a local keyword store on any Hindsight error, and always reports which backend is active.
- `core/agent.py` — runs `investigate()` twice per report (memory off / on) for the direct comparison,
  and flags whether a resolution was memory-assisted.
- `scripts/seed_memory.py` — idempotent seeding of starter incidents (safe to re-run; use `--force`
  to re-seed on purpose).

## Screenshots
_Add screenshots here: the without/with-memory comparison, the recalled-memories panel, the
Resolve & Learn confirmation, and the Memory tab._

## Demo flow (60–90 seconds)
1. **Report** a fresh incident, e.g. Payment API / 502 Bad Gateway / after deployment. Point out the
   generic "without memory" answer next to the specific "with memory" one.
2. **Resolve & Learn**: enter root cause "Nginx upstream port changed", fix "reverted nginx.conf +
   reload", failed attempt "restarting pods". Watch the "🧠 Agent learned from this incident" panel.
3. **Report** a new, similarly-worded incident. The "with memory" column now names the earlier root
   cause, recommends the fix that worked, and explicitly avoids the fix that failed.
4. Open **Memory** and search `502 after deployment` to show the raw retained/recalled memory.
5. Open **Dashboard** to show the memory-assisted resolutions metric and the learning timeline.

## Before vs after memory — concrete example
| | Without memory | With Hindsight memory |
|---|---|---|
| Root cause | Generic guess from symptoms alone | Names the exact prior root cause |
| Actions | Generic checklist | Specific steps that worked before |
| Failed attempts | Not considered | Explicitly avoided |
| Confidence | Lower | Higher, and explained |

## Technology
- Python, Streamlit (UI)
- Hindsight (memory — retain / recall), required by the challenge
- Groq (`openai/gpt-oss-120b` by default) for analysis, with a heuristic fallback if the LLM call
  or JSON parsing fails
- Synthetic incident data in `data/seed_incidents.json`

## Installation
```bash
python -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in your Hindsight + Groq keys
python -m scripts.seed_memory
streamlit run app.py
```
Without keys, the app still runs on a local fallback memory + heuristic, clearly labelled in the UI
header (⚠️ shown when not on Hindsight).

## Environment variables
See `.env.example`:
- `HINDSIGHT_BASE_URL`, `HINDSIGHT_API_KEY`, `HINDSIGHT_BANK_ID`
- `GROQ_API_KEY`, `GROQ_MODEL`

**Never commit `.env`.** Only `.env.example` should be in the repository — see `.gitignore`.

## Future improvements
- Use Hindsight's `reflect` operation to synthesize accumulated experience across many incidents,
  not just recall individual matches.
- Pull resolved tickets automatically from Jira / PagerDuty / ServiceNow instead of manual entry.
- Multi-team memory banks, so different services or squads build their own incident history.
