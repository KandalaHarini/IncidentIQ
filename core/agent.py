from .hindsight_memory import Memory
from .llm import analyze

memory = Memory()


def investigate(incident: dict, use_memory: bool = True) -> dict:
    query = f"{incident['service']} {incident['error']} {incident['description']} {incident.get('recent_change','')}"
    recalled_parsed = memory.recall_parsed(query) if use_memory else []
    recalled_raw = [m["raw"] for m in recalled_parsed]
    result = analyze(incident, recalled_raw)
    result["recalled"] = recalled_raw
    result["recalled_parsed"] = recalled_parsed
    result["memory_assisted"] = bool(recalled_parsed)
    return result


def resolve_and_learn(incident: dict, root_cause: str, solution: str, failed: str, worked: bool) -> dict:
    inc = {**incident, "root_cause": root_cause, "solution": solution,
           "failed_attempts": failed, "worked": worked, "status": "resolved"}
    stored_in_hindsight = memory.retain(inc)
    inc["stored_in_hindsight"] = stored_in_hindsight
    return inc
