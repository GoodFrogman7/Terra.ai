from typing import Dict, Any
import asyncio

try:
    from langgraph.graph import StateGraph, END
    _HAS_LG = True
except Exception:
    _HAS_LG = False

from core.graph.nodes import (
    intake, kb_retrieve, answer_from_kb,
    research_plan, web_research, synthesize_research,
    policy_gate, kb_no_answer
)

def route_after_kb(state: Dict[str, Any]) -> str:
    conf = float(state.get("kb_conf", 0.0))
    threshold = float(state.get("KB_THRESHOLD", 0.62))
    force = bool(state.get("force_research", False))
    web_enabled = bool(state.get("web_enabled", True))
    if (conf >= threshold) and not force:
        return "answer_from_kb"
    if not web_enabled:
        return "kb_no_answer"
    return "research_plan"

if _HAS_LG:
    graph = StateGraph(dict)
    graph.add_node("intake", intake)
    graph.add_node("kb_retrieve", kb_retrieve)
    graph.add_node("answer_from_kb", answer_from_kb)
    graph.add_node("kb_no_answer", kb_no_answer)
    graph.add_node("research_plan", research_plan)
    graph.add_node("web_research", web_research)
    graph.add_node("synthesize_research", synthesize_research)
    graph.add_node("policy_gate", policy_gate)

    graph.set_entry_point("intake")
    graph.add_edge("intake", "kb_retrieve")
    graph.add_conditional_edges("kb_retrieve", route_after_kb, {
        "answer_from_kb": "answer_from_kb",
        "kb_no_answer": "kb_no_answer",
        "research_plan": "research_plan",
    })
    graph.add_edge("answer_from_kb", "policy_gate")
    graph.add_edge("kb_no_answer", "policy_gate")
    graph.add_edge("research_plan", "web_research")
    graph.add_edge("web_research", "synthesize_research")
    graph.add_edge("synthesize_research", "policy_gate")
    graph.add_edge("policy_gate", END)
    compiled = graph.compile()
else:
    class _Compiled:
        def invoke(self, state: Dict[str, Any]) -> Dict[str, Any]:
            s = intake(state)
            s = kb_retrieve(s)
            route = route_after_kb(s)
            if route == "answer_from_kb":
                s = answer_from_kb(s)
                s = policy_gate(s)
                return s
            if route == "kb_no_answer":
                from core.graph.nodes import kb_no_answer as _kb_no
                s = _kb_no(s)
                s = policy_gate(s)
                return s
            s = research_plan(s)
            s = web_research(s)
            s = synthesize_research(s)
            s = policy_gate(s)
            return s

        async def ainvoke(self, state: Dict[str, Any]) -> Dict[str, Any]:
            return await asyncio.to_thread(self.invoke, state)

    compiled = _Compiled()

def graph_dot() -> str:
    return r"""
digraph G {
  rankdir=LR;
  node [shape=box, style=rounded];

  intake -> kb_retrieve;
  kb_retrieve -> answer_from_kb [label="conf >= τ (intent-adjusted)"];
  kb_retrieve -> kb_no_answer  [label="conf < τ & web=off"];
  kb_retrieve -> research_plan [label="conf < τ & web=on or force"];
  research_plan -> web_research;
  web_research -> synthesize_research;
  answer_from_kb -> policy_gate;
  kb_no_answer   -> policy_gate;
  synthesize_research -> policy_gate;
  policy_gate -> end;

  end [shape=doublecircle];
}
""".strip()
