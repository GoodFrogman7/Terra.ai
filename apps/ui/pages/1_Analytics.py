"""
Terra.ai — Analytics Dashboard
Resolution-rate and grounding metrics: how many queries were answered from
the verified KB vs web fallback vs ungrounded model knowledge.
"""
import os
import requests
import streamlit as st

API_BASE = os.getenv("COPILOT_API_BASE", "http://127.0.0.1:8000")

st.set_page_config(page_title="Terra.ai — Analytics", layout="wide")
st.title("📊 Terra.ai Analytics")
st.caption("Resolution and grounding metrics across all chat interactions.")


def _fetch_analytics(domain: str | None = None) -> dict:
    try:
        params = {"domain": domain} if domain else {}
        token = st.session_state.get("access_token")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        r = requests.get(f"{API_BASE}/analytics/summary", params=params, headers=headers, timeout=10)
        if r.status_code == 401:
            st.warning("Please log in on the main page first.")
            st.stop()
        if r.ok:
            return r.json()
    except Exception as e:
        st.error(f"Could not reach API: {e}")
    return {}


domain_filter = st.selectbox("Domain", ["All", "finance", "healthcare"])
data = _fetch_analytics(None if domain_filter == "All" else domain_filter)

if not data or not data.get("summary", {}).get("total_interactions"):
    st.info("No interactions logged yet. Ask some questions in the chat first.")
    st.stop()

summary = data["summary"]
total = summary["total_interactions"]

# Headline metrics
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total queries", total)
col2.metric("Grounded rate", f"{summary['grounded_rate'] * 100:.0f}%",
            help="Share of answers backed by KB or web sources (vs model-only)")
col3.metric("Citation rate", f"{summary['citation_rate'] * 100:.0f}%",
            help="Share of answers that carried at least one citation")
col4.metric("Escalation rate", f"{summary['escalation_rate'] * 100:.0f}%",
            help="Share of queries flagged for human review by the policy gate")

if summary.get("avg_kb_confidence") is not None:
    st.caption(f"Average KB retrieval confidence: {summary['avg_kb_confidence']:.3f}")

# Source breakdown
st.subheader("Answer sources")
by_source = summary.get("by_source", {})
if by_source:
    st.bar_chart(by_source)

# Domain breakdown (only meaningful for "All")
if domain_filter == "All":
    by_domain = summary.get("by_domain", {})
    if len(by_domain) > 1:
        st.subheader("Queries by domain")
        st.bar_chart(by_domain)

# Recent interactions table
st.subheader("Recent interactions")
recent = data.get("recent", [])
if recent:
    st.dataframe(
        [
            {
                "Time (UTC)": r["ts"][:19].replace("T", " "),
                "Domain": r["domain"],
                "Source": r["source"],
                "KB conf": f"{r['kb_conf']:.3f}" if r.get("kb_conf") is not None else "—",
                "Citations": r["num_citations"],
                "Flags": ", ".join(r.get("policy_flags", [])) or "—",
            }
            for r in recent
        ],
        use_container_width=True,
    )
