import json, os, re
from dotenv import load_dotenv
load_dotenv()

SYSTEM = """You are IncidentIQ, an SRE assistant. Given a NEW incident and optionally MEMORIES of past
incidents, return ONLY a JSON object with keys:
severity (LOW|MEDIUM|HIGH|CRITICAL), likely_root_cause (string),
recommended_actions (list of 3-5 ordered strings), confidence (0-100 int),
memory_influence (string: how past incidents changed your advice, or 'No relevant memory').
If memories contain a root cause/solution for a matching pattern, prioritise it, and avoid solutions
that memory says FAILED — mention that avoidance explicitly in memory_influence
(e.g. "skipped restarting pods, which failed last time"). Never invent incident IDs."""


def _parse(text: str) -> dict:
    text = re.sub(r"```json|```", "", text).strip()
    return json.loads(re.search(r"\{.*\}", text, re.S).group(0))


def analyze(incident: dict, memories: list[str]) -> dict:
    prompt = f"NEW INCIDENT:\n{json.dumps(incident, indent=2)}\n\nMEMORIES:\n" + (
        "\n".join(f"- {m}" for m in memories) if memories else "(none)")
    key = os.getenv("GROQ_API_KEY")
    if key:
        try:
            from groq import Groq
            r = Groq(api_key=key).chat.completions.create(
                model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
                messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
                temperature=0.2)
            return _parse(r.choices[0].message.content)
        except Exception as e:  # malformed JSON / API errors -> graceful fallback
            print("LLM error, using heuristic:", e)
    return _heuristic(incident, memories)


def _heuristic(incident, memories):
    if memories:
        top = memories[0]
        rc = re.search(r"ROOT CAUSE: (.*?)\. SOLUTION", top, re.S)
        sol = re.search(r"SOLUTION APPLIED: (.*?)\. FAILED", top, re.S)
        failed = re.search(r"FAILED ATTEMPTS: (.*?)\. OUTCOME", top, re.S)
        actions = [f"Apply previous fix: {sol.group(1) if sol else 'see memory'}",
                   "Verify the recent change diff", "Confirm with health checks"]
        influence = "Matched a past incident and reused its root cause/fix."
        if failed and failed.group(1) and "none" not in failed.group(1).lower():
            influence += f" Avoided a previously failed attempt: {failed.group(1)}."
        return {"severity": incident["severity"],
                "likely_root_cause": rc.group(1) if rc else "See recalled incident",
                "recommended_actions": actions,
                "confidence": 85, "memory_influence": influence}
    return {"severity": incident["severity"], "likely_root_cause": "Unknown - generic triage",
            "recommended_actions": ["Check service status", "Check network and gateway", "Review logs",
                                    "Roll back the latest deployment"],
            "confidence": 35, "memory_influence": "No relevant memory"}
