"""Memory layer. Uses Hindsight when configured; falls back to a local
keyword-overlap store on any error, so a demo never crashes (clearly
labelled in the UI via Memory.backend).

Two things worth knowing:
1. A fresh Hindsight client is created for every retain/recall call rather
   than reused, because long-lived clients break across Streamlit reruns
   (each rerun can land on a different asyncio event loop, which surfaces
   as "Timeout context manager should be used inside a task").
2. Hindsight can return an incident's memory as several small facts rather
   than one blob (e.g. root cause and solution as separate snippets).
   recall_parsed() pulls extra raw results and MERGES snippets that share
   the same incident id, so root cause + solution both show up together
   instead of one field being blank."""
import json, os, re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LOCAL_FILE = DATA_DIR / "local_memory.json"

FIELD_PATTERNS = {
    "id": r"Incident (\S+) on service",
    "service": r"on service '([^']+)'",
    "symptom": r"Symptom: (.*?)\. Description:",
    "root_cause": r"ROOT CAUSE: (.*?)\. SOLUTION APPLIED:",
    "solution": r"SOLUTION APPLIED: (.*?)\. FAILED ATTEMPTS:",
    "failed_attempts": r"FAILED ATTEMPTS: (.*?)\. OUTCOME:",
}


def incident_to_memory(inc: dict) -> str:
    """Turn a resolved incident into a narrative Hindsight can extract facts from."""
    return (
        f"Incident {inc['id']} on service '{inc['service']}' ({inc['environment']}), "
        f"severity {inc['severity']}. Symptom: {inc['error']}. "
        f"Description: {inc['description']} Recent change: {inc.get('recent_change') or 'none'}. "
        f"ROOT CAUSE: {inc['root_cause']}. "
        f"SOLUTION APPLIED: {inc['solution']}. "
        f"FAILED ATTEMPTS: {inc.get('failed_attempts') or 'none recorded'}. "
        f"OUTCOME: {'resolved' if inc.get('worked', True) else 'not resolved'}."
    )


def parse_memory(text: str) -> dict:
    """Best-effort parse of a stored memory string back into fields, for display."""
    out = {"raw": text}
    for field, pat in FIELD_PATTERNS.items():
        m = re.search(pat, text, re.S)
        out[field] = m.group(1).strip() if m else None
    return out


def merge_by_incident(parsed_list: list[dict]) -> list[dict]:
    """Combine multiple recalled snippets that belong to the same incident id,
    so a root-cause-only snippet and a solution-only snippet about the same
    incident end up as one entry with both fields filled."""
    merged: dict[str, dict] = {}
    order: list[str] = []
    fields = ("root_cause", "solution", "failed_attempts", "symptom", "service", "id")
    for p in parsed_list:
        key = p.get("id") or p["raw"]
        if key not in merged:
            merged[key] = dict(p)
            order.append(key)
        else:
            for f in fields:
                if not merged[key].get(f) and p.get(f):
                    merged[key][f] = p[f]
            if p["raw"] not in merged[key]["raw"]:
                merged[key]["raw"] += "\n\n" + p["raw"]
    return [merged[k] for k in order]


class Memory:
    def __init__(self):
        self.bank = os.getenv("HINDSIGHT_BANK_ID", "incidentiq")
        self.url = os.getenv("HINDSIGHT_BASE_URL")
        self.key = os.getenv("HINDSIGHT_API_KEY")
        self.hindsight_configured = bool(self.url and (self.key or "localhost" in self.url))
        self.backend = "hindsight" if self.hindsight_configured else "local-fallback"

    def _new_client(self):
        from hindsight_client import Hindsight
        return Hindsight(base_url=self.url, api_key=self.key) if self.key else Hindsight(base_url=self.url)

    # ---------- retain ----------
    def retain(self, inc: dict) -> bool:
        """Store a resolved incident. Returns True if it went into Hindsight,
        False if it fell back to local storage (e.g. Hindsight errored)."""
        text = incident_to_memory(inc)
        if self.hindsight_configured:
            try:
                client = self._new_client()
                client.retain(bank_id=self.bank, content=text, context="resolved production incident")
                self.backend = "hindsight"
                return True
            except Exception as e:
                print("Hindsight retain failed, saving locally instead:", e)
                self.backend = "local-fallback (retain failed)"
        data = self._load(); data.append(text)
        LOCAL_FILE.write_text(json.dumps(data, indent=2))
        return False

    # ---------- recall ----------
    def recall(self, query: str, k: int = 4) -> list[str]:
        """Return up to k raw memory strings relevant to the query."""
        if self.hindsight_configured:
            try:
                client = self._new_client()
                res = client.recall(bank_id=self.bank, query=query)
                items = getattr(res, "results", res) or []
                out = [getattr(r, "text", None) or (r.get("text") if isinstance(r, dict) else str(r))
                       for r in items]
                self.backend = "hindsight"
                return out[:k]
            except Exception as e:
                print("Hindsight recall failed, using local fallback:", e)
                self.backend = "local-fallback (recall failed)"
        q = set(re.findall(r"\w+", query.lower()))
        scored = sorted(((len(q & set(re.findall(r"\w+", m.lower()))), m) for m in self._load()), reverse=True)
        return [m for s, m in scored if s > 2][:k]

    def recall_parsed(self, query: str, k: int = 4) -> list[dict]:
        """Recall + parse + merge snippets about the same incident, so root
        cause and solution show together even if Hindsight split them up."""
        raw = self.recall(query, k=max(k * 3, 8))
        parsed = [parse_memory(m) for m in raw]
        return merge_by_incident(parsed)[:k]

    @staticmethod
    def _load() -> list:
        return json.loads(LOCAL_FILE.read_text()) if LOCAL_FILE.exists() else []