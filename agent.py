# -*- coding: utf-8 -*-
"""분류 → 판정 → 근거 조회·답변 → 검증을 하나의 그래프로 잇는다.

    classify → gate ─┬─ HANDLE ──────→ answer → verify ─┬─ 통과 ─────────→ END
                     ├─ OUT_OF_SCOPE → finish           ├─ 실패, 재시도 남음 → answer
                     └─ ESCALATE ────→ finish           └─ 실패, 재시도 없음 → finish(넘김)
"""
from typing import List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from answer import answer_with_tools
from config import VERIFY_RETRY
from context import ESCALATE_TOOL
from guardrail import feedback_text, verify
from prompts import LOW_CONF_MESSAGE, OUT_OF_SCOPE_MESSAGE, VERIFY_FAIL_MESSAGE
from router import classify, gate


class AgentState(TypedDict, total=False):
    question: str
    route: str
    confidence: float
    reason: str
    decision: str              # gate: HANDLE / ESCALATE / OUT_OF_SCOPE
    action: str                # 최종 행동: ANSWER / ESCALATE / OUT_OF_SCOPE
    tools: List[str]           # 호출한 도구 (순서대로)
    sections: list             # 조회한 조항 원문
    answer: str
    verify: Optional[dict]     # 마지막 검증 결과
    history: list              # 시도별 (답변, 검증) — 데모·실패 분석용
    attempts: int
    loop_limit: bool           # 도구 호출 루프 상한에 걸림


def node_answer(state: AgentState) -> AgentState:
    feedback = feedback_text(state["verify"]) if state.get("verify") else None
    text, called, sections, escalated = answer_with_tools(state["question"], state["route"], feedback)
    if text is None:     # 도구 루프 상한
        return {"action": "ESCALATE", "tools": called, "sections": [], "answer": LOW_CONF_MESSAGE,
                "loop_limit": True, "attempts": state.get("attempts", 0) + 1}
    return {"tools": called, "sections": sections, "answer": text,
            "action": "ESCALATE" if escalated else "ANSWER",
            "attempts": state.get("attempts", 0) + 1}


def node_verify(state: AgentState) -> AgentState:
    result = verify(state["answer"], state["question"], state["sections"], state["tools"],
                    state["action"] == "ESCALATE")
    history = (state.get("history") or []) + [{"answer": state["answer"], "tools": state["tools"],
                                               "verify": result}]
    return {"verify": result, "history": history}


def node_finish(state: AgentState) -> AgentState:
    """모델 답변 없이 끝나는 경로 — 범위 밖, 확신도 미달, 검증 재실패."""
    if state["decision"] == "OUT_OF_SCOPE":
        return {"action": "OUT_OF_SCOPE", "tools": [], "sections": [], "answer": OUT_OF_SCOPE_MESSAGE}
    if state["decision"] == "ESCALATE":
        return {"action": "ESCALATE", "tools": [ESCALATE_TOOL], "sections": [], "answer": LOW_CONF_MESSAGE}
    # 검증 재실패: 조회한 도구 기록은 남기고 답변만 넘김 문구로 바꾼다
    tools = state["tools"] + ([ESCALATE_TOOL] if ESCALATE_TOOL not in state["tools"] else [])
    return {"action": "ESCALATE", "tools": tools, "answer": VERIFY_FAIL_MESSAGE}


def after_gate(state: AgentState) -> str:
    return "answer" if state["decision"] == "HANDLE" else "finish"


def after_verify(state: AgentState) -> str:
    if state["verify"]["ok"]:
        return END
    return "answer" if state["attempts"] <= VERIFY_RETRY else "finish"


def after_answer(state: AgentState) -> str:
    return END if state.get("loop_limit") else "verify"


def build_agent():
    g = StateGraph(AgentState)
    g.add_node("classify", classify)
    g.add_node("gate", gate)
    g.add_node("answer", node_answer)
    g.add_node("verify", node_verify)
    g.add_node("finish", node_finish)
    g.add_edge(START, "classify")
    g.add_edge("classify", "gate")
    g.add_conditional_edges("gate", after_gate, {"answer": "answer", "finish": "finish"})
    g.add_conditional_edges("answer", after_answer, {"verify": "verify", END: END})
    g.add_conditional_edges("verify", after_verify, {"answer": "answer", "finish": "finish", END: END})
    g.add_edge("finish", END)
    return g.compile()


agent_app = build_agent()


def run(question: str) -> dict:
    """문의 한 줄을 파이프라인에 통과시킨다."""
    return agent_app.invoke({"question": question})
