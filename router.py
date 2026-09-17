# -*- coding: utf-8 -*-
"""의도 분류 라우터. classify(모델의 일)와 gate(정책의 일)를 나눈다.

둘을 나눠 두면 임계값만 바꿀 때 모델을 다시 부르지 않아도 되고,
"카테고리를 고르는 일"과 "확신이 없을 때 넘기는 판단"을 따로 잴 수 있다.
"""
from typing import Literal, TypedDict

from langchain.chat_models import init_chat_model
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from config import CONF_THRESHOLD, MODEL
from prompts import ROUTE_GUIDE


class RouterState(TypedDict, total=False):
    question: str
    route: str          # classify 가 채운다
    confidence: float   # classify 가 채운다
    reason: str         # classify 가 채운다
    decision: str       # gate 가 채운다 — HANDLE / ESCALATE / OUT_OF_SCOPE


class RouteDecision(BaseModel):
    """이용자 문의 한 건의 라우팅 판단."""

    route: Literal["SCOPE", "ACCOUNT_PRIVACY", "LISTING", "INTERVIEW", "REPORT", "OTHER"] = Field(
        description="문의를 배정할 라우트. 6개 값 중 하나.")
    confidence: float = Field(
        ge=0.0, le=1.0, description="판단의 확신도. 두 라우트 사이에서 애매하면 0.5 미만.")
    reason: str = Field(description="그 라우트로 판단한 근거 한 문장.")


_chain = None


def classify(state: RouterState) -> RouterState:
    """노드 ① 분류 — LLM 구조화 출력."""
    global _chain
    if _chain is None:
        _chain = init_chat_model(MODEL, temperature=0, timeout=60, max_retries=2
                                 ).with_structured_output(RouteDecision)
    d = _chain.invoke([("system", ROUTE_GUIDE), ("human", f"이용자 문의: {state['question']}")])
    return {"route": d.route, "confidence": d.confidence, "reason": d.reason}


def gate(state: RouterState, threshold: float = CONF_THRESHOLD) -> RouterState:
    """노드 ② 판정 — 확신도와 범위를 보고 처리/넘기기/범위밖을 정한다."""
    if state["confidence"] < threshold:
        return {"decision": "ESCALATE"}
    if state["route"] == "OTHER":
        return {"decision": "OUT_OF_SCOPE"}
    return {"decision": "HANDLE"}


def build():
    g = StateGraph(RouterState)
    g.add_node("classify", classify)
    g.add_node("gate", gate)
    g.add_edge(START, "classify")
    g.add_edge("classify", "gate")
    g.add_edge("gate", END)
    return g.compile()


router_app = build()
