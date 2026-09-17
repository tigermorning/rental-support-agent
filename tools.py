# -*- coding: utf-8 -*-
"""근거 조회 도구. 각 도구는 약관·처리방침·가이드라인의 정해진 조항 묶음을 원문 그대로 돌려준다.

- 도구 설명(description)이 모델이 읽는 유일한 안내다. 여기를 고치면 도구 선택이 달라진다.
- 조회 도구는 인자가 없다. 같은 도구는 언제 불러도 같은 조항을 돌려준다 → 채점이 결정적이다.
"""
from langchain_core.tools import StructuredTool

from context import (ESCALATE_TOOL, TOOL_DESCRIPTIONS, TOOL_SECTIONS, sections_for_tool)


def _lookup(name):
    def fn() -> dict:
        return {"sections": sections_for_tool(name)}
    fn.__name__ = name
    return fn


def escalate_to_operator(reason: str) -> dict:
    """운영자에게 넘긴다. 실제 접수 시스템이 없어 넘김 사실만 돌려준다."""
    return {"escalated": True, "reason": reason,
            "message": "문의 내용을 운영자에게 전달했습니다. 확인 후 안내드리겠습니다."}


FUNCTIONS = {name: _lookup(name) for name in TOOL_SECTIONS}
FUNCTIONS[ESCALATE_TOOL] = escalate_to_operator

LC_TOOLS = {
    name: StructuredTool.from_function(
        FUNCTIONS[name], name=name,
        description=f"조항 원문 조회: {TOOL_DESCRIPTIONS[name]}. 반환 조항: "
                    + ", ".join(f"{d} {n}" for d, n in TOOL_SECTIONS[name]))
    for name in TOOL_SECTIONS
}
LC_TOOLS[ESCALATE_TOOL] = StructuredTool.from_function(
    escalate_to_operator, name=ESCALATE_TOOL,
    description="운영자에게 넘긴다. 조회한 조항에 물은 사실(기간·건수·연락처·기능·일정 등)이 없을 때, "
                "또는 이용자 본인의 신청·신고·매물·계정 상태를 확인해야 할 때 부른다. "
                "reason 에 넘기는 이유를 한 문장으로 적는다.")
