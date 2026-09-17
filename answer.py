# -*- coding: utf-8 -*-
"""답변 생성. 모델이 라우트에 허용된 도구만 골라 부르는 그래프다.

라우트별로 다른 도구 목록을 모델에 붙인다. 모델이 다른 라우트의 조항을 부를 방법 자체가 없으므로
"카테고리마다 필요한 근거만 프롬프트에 들어간다"가 구조로 보장된다.
"""
from typing import Annotated, TypedDict

from langchain.chat_models import init_chat_model
from langgraph.errors import GraphRecursionError
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from config import ANSWER_MODEL, MAX_TOOL_TURNS
from context import ESCALATE_TOOL, TOOL_SECTIONS, sections_for_tool, tools_for_route
from prompts import ANSWER_RULES, answer_examples
from tools import LC_TOOLS

_llms = {}


def _llm(route):
    if route not in _llms:
        # reasoning_effort="none": 이 등급 모델은 추론 모드와 도구 호출을 함께 쓰면 400 을 돌려준다
        base = init_chat_model(ANSWER_MODEL, temperature=0, reasoning_effort="none",
                               timeout=60, max_retries=2)
        _llms[route] = base.bind_tools([LC_TOOLS[n] for n in tools_for_route(route)])
    return _llms[route]


class ToolState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    route: str


def agent(state: ToolState) -> ToolState:
    return {"messages": [_llm(state["route"]).invoke(state["messages"])]}


def _build():
    g = StateGraph(ToolState)
    g.add_node("agent", agent)
    g.add_node("tools", ToolNode(list(LC_TOOLS.values())))
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", tools_condition)
    g.add_edge("tools", "agent")
    return g.compile()


tool_app = _build()


def system_prompt(route, feedback=None):
    parts = [ANSWER_RULES, answer_examples(route)]
    if feedback:
        parts.append("[직전 답변이 검증에 걸렸다. 아래 문제를 고쳐 다시 답한다]\n" + feedback)
    return "\n\n".join(p for p in parts if p)


def answer_with_tools(question, route, feedback=None, max_turns=MAX_TOOL_TURNS):
    """(답변, 호출한 도구 이름 목록, 조회한 조항 목록, 넘김 여부)를 돌려준다."""
    init = {"route": route,
            "messages": [("system", system_prompt(route, feedback)), ("human", question)]}
    try:
        out = tool_app.invoke(init, {"recursion_limit": 2 * max_turns + 1})
    except GraphRecursionError:     # 상한에 걸린 경우만 넘긴다. 다른 예외는 원인을 보려고 잡지 않는다
        return None, [ESCALATE_TOOL], [], True

    called, sections, seen = [], [], set()
    for m in out["messages"]:
        for tc in getattr(m, "tool_calls", None) or []:
            if tc["name"] not in called:
                called.append(tc["name"])
    # 조회한 조항은 도구 이름으로 다시 계산한다 — 도구가 결정적이라 메시지 파싱보다 확실하다
    for name in called:
        if name in TOOL_SECTIONS:
            for s in sections_for_tool(name):
                if s["id"] not in seen:
                    seen.add(s["id"])
                    sections.append(s)
    return out["messages"][-1].content, called, sections, ESCALATE_TOOL in called
