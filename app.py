import json
from pathlib import Path
import pandas as pd
import streamlit as st
from core.agent import investigate, resolve_and_learn, memory

st.set_page_config(page_title="IncidentIQ", page_icon="🚨", layout="wide")
DB = Path("data/incidents.json")


def load():
    return json.loads(DB.read_text()) if DB.exists() else json.loads(Path("data/seed_incidents.json").read_text())


def save(x):
    DB.write_text(json.dumps(x, indent=2))


if "incidents" not in st.session_state:
    st.session_state.incidents = load()
for i in st.session_state.incidents:
    i.setdefault("status", "resolved")

st.title("🚨 IncidentIQ")
backend = memory.backend
badge = "🟢" if backend == "hindsight" else "🟠"
st.caption(f"AI incident resolution agent that learns from past incidents · "
           f"{badge} memory backend: **{backend}**")
if backend != "hindsight":
    st.warning("Running on local fallback memory, not Hindsight. Check HINDSIGHT_BASE_URL / "
               "HINDSIGHT_API_KEY in .env and your Hindsight Cloud credits before demoing.")

tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "🔍 Report & Investigate", "✅ Resolve & Learn", "🧠 Memory"])

# ---------------------------------------------------------------- Dashboard
with tab1:
    df = pd.DataFrame(st.session_state.incidents)
    resolved = [i for i in st.session_state.incidents if i.get("root_cause")]
    memory_assisted = [i for i in resolved if i.get("used_memory")]

    c = st.columns(5)
    c[0].metric("Total incidents", len(df))
    c[1].metric("Resolved", int((df.status == "resolved").sum()))
    c[2].metric("Recurring services", int(df.service.duplicated().sum()))
    c[3].metric("Memories retained", len(resolved))
    c[4].metric("🧠 Memory-assisted resolutions", len(memory_assisted))

    st.dataframe(df[["id", "service", "severity", "error", "status"]], use_container_width=True, hide_index=True)

    if resolved:
        st.subheader("Agent learning timeline")
        for i in resolved:
            tag = "🧠 recalled memory →" if i.get("used_memory") else "🆕 first time seen →"
            st.write(f"**{i['id']}** ({i['service']}) {tag} learned: *{i['root_cause']}*")

# ---------------------------------------------------------- Report & Investigate
with tab2:
    examples = {f"{i['id']} - {i['service']}: {i['error']}": i for i in st.session_state.incidents}
    defaults = {"f_service": "Payment API", "f_env": "production", "f_error": "502 Bad Gateway",
                "f_sev": "HIGH", "f_desc": "Payment API returning 502 again right after today's deployment.",
                "f_change": "Deployment v3.21 touched gateway config"}
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

    def load_example():
        e = examples.get(st.session_state.example)
        if e:
            st.session_state.f_service = e["service"]
            st.session_state.f_env = e["environment"]
            st.session_state.f_error = e["error"]
            st.session_state.f_sev = e["severity"]
            st.session_state.f_desc = e["description"]
            st.session_state.f_change = e.get("recent_change", "")

    st.selectbox("Load an incident from the dashboard", ["-- write my own --"] + list(examples),
                 key="example", on_change=load_example)

    with st.form("report"):
        a, b = st.columns(2)
        service = a.text_input("Service", key="f_service")
        env = a.selectbox("Environment", ["production", "staging"], key="f_env")
        error = b.text_input("Error message", key="f_error")
        sev = b.selectbox("Severity", ["LOW", "MEDIUM", "HIGH", "CRITICAL"], key="f_sev")
        desc = st.text_area("Description", key="f_desc")
        change = st.text_input("Recent change / deployment", key="f_change")
        go = st.form_submit_button("Investigate")

    if go:
        inc = {"id": f"INC-{1000 + len(st.session_state.incidents) + 1}", "service": service, "environment": env,
               "severity": sev, "error": error, "description": desc, "recent_change": change, "status": "open"}
        with st.spinner("Recalling from memory and analysing..."):
            st.session_state.current = inc
            st.session_state.without = investigate(inc, use_memory=False)
            st.session_state.with_mem = investigate(inc, use_memory=True)

    if "current" in st.session_state:
        L, R = st.columns(2)
        with L:
            r = st.session_state.without
            st.subheader("❌ Without memory")
            st.write(f"**Severity:** {r['severity']} · **Confidence:** {r['confidence']}%")
            st.write(f"**Likely root cause:** {r['likely_root_cause']}")
            st.write("**Recommended actions**")
            for n, x in enumerate(r["recommended_actions"], 1):
                st.write(f"{n}. {x}")
            st.info(f"Memory influence: {r['memory_influence']}")

        with R:
            r = st.session_state.with_mem
            st.subheader("✅ With Hindsight memory")
            st.write(f"**Severity:** {r['severity']} · **Confidence:** {r['confidence']}%")
            st.write(f"**Likely root cause:** {r['likely_root_cause']}")
            st.write("**Recommended actions**")
            for n, x in enumerate(r["recommended_actions"], 1):
                st.write(f"{n}. {x}")
            st.success(f"Memory influence: {r['memory_influence']}")

            recalled = r.get("recalled_parsed", [])
            st.markdown(f"**🧠 {len(recalled)} relevant past incident(s) recalled**")
            for m in recalled:
                label = f"{m.get('id') or 'past incident'} — {m.get('service') or ''}"
                with st.expander(label if label.strip("— ") else "Recalled memory"):
                    if m.get("root_cause") or m.get("solution"):
                        st.write(f"**Previous root cause:** {m.get('root_cause') or '—'}")
                        st.write(f"**Previous successful solution:** {m.get('solution') or '—'}")
                        if m.get("failed_attempts") and "none" not in (m["failed_attempts"] or "").lower():
                            st.write(f"**Previously failed attempt (avoided):** {m['failed_attempts']}")
                    else:
                        st.caption("Hindsight returned this as a summary; showing raw text:")
                        st.write(m["raw"])

        st.session_state.setdefault("inc_list_added", set())
        if st.session_state.current["id"] not in st.session_state.inc_list_added:
            cur = dict(st.session_state.current)
            cur["used_memory"] = bool(st.session_state.with_mem.get("recalled"))
            st.session_state.incidents.append(cur)
            st.session_state.inc_list_added.add(cur["id"])

# ---------------------------------------------------------------- Resolve & Learn
with tab3:
    open_inc = [i for i in st.session_state.incidents if i["status"] == "open"]
    if not open_inc:
        st.info("No open incidents. Report one in the previous tab.")
    else:
        pick = st.selectbox("Open incident", [f"{i['id']} - {i['service']}: {i['error']}" for i in open_inc])
        inc = next(i for i in open_inc if pick.startswith(i["id"]))
        rc = st.text_area("Actual root cause")
        sol = st.text_area("Solution used")
        failed = st.text_input("What didn't work?")
        worked = st.checkbox("Solution worked", True)
        if st.button("Resolve & store in memory") and rc and sol:
            done = resolve_and_learn(inc, rc, sol, failed, worked)
            inc.update(done)
            save(st.session_state.incidents)

            where = "Hindsight" if done.get("stored_in_hindsight") else "local fallback memory"
            st.success(f"Stored in {where}. The agent will use this the next time a similar incident appears.")
            st.markdown("#### 🧠 Agent learned from this incident")
            st.write("✓ Root cause retained")
            st.write("✓ Successful solution retained")
            st.write(f"✓ Failed attempt retained: *{failed}*" if failed else "✓ Failed attempts: none recorded")
            st.write("✓ Deployment / change context retained")
            st.caption("This experience can now influence future investigations for similar incidents.")

# ---------------------------------------------------------------- Memory
# ---------------------------------------------------------------- Memory
with tab4:
    st.write("Search everything the agent has learned:")
    q = st.text_input("Query memory", "502 after deployment")
    if q:
        hits = memory.recall_parsed(q, k=6)
        st.write(f"{len(hits)} memories recalled")
        for m in hits:
            label = f"{m.get('id') or 'memory'} — {m.get('service') or ''}"
            with st.expander(label if label.strip("— ") else "Recalled memory"):
                if m.get("root_cause") or m.get("solution"):
                    st.write(f"**Symptom:** {m.get('symptom') or '—'}")
                    st.write(f"**Root cause:** {m.get('root_cause') or '—'}")
                    st.write(f"**Solution:** {m.get('solution') or '—'}")
                    st.write(f"**Failed attempts:** {m.get('failed_attempts') or '—'}")
                else:
                    st.caption("Hindsight returned this as a summary rather than the original "
                               "template, so showing the raw text instead:")
                    st.write(m["raw"])
