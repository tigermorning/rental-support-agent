# -*- coding: utf-8 -*-
"""답변 적절성 채점기. 표현이 아니라 사실을 본다.

문항의 must(반드시 담을 사실)와 forbid(말하면 안 되는 내용)를 하나씩 판정하게 하고,
판정마다 답변 속 근거 문장을 적게 한다. 근거가 남아야 틀린 판정을 사람이 찾을 수 있다.

채점기 자체의 타당성은 `python evaluate.py --validate` 로 확인한다.
"""
import json
import os
from typing import List

from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field

from config import ANSWER_MODEL

JUDGE_MODEL = os.environ.get("RENTAL_JUDGE_MODEL", ANSWER_MODEL)

JUDGE_RULES = """너는 고객 응대 답변 채점자다. 답변이 채점 기준의 사실을 담았는지, 금지 내용을 말했는지 판정한다.

[판정 원칙]
- 표현이 아니라 사실을 본다. 어순·단어·존댓말이 달라도 같은 뜻이면 담은 것이다
- 답변에 적힌 내용만 본다. 네가 아는 지식으로 답변을 보충하거나 옳고 그름을 따지지 않는다

[must — 반드시 담을 사실]
- covered=true: 답변이 그 사실을 같은 뜻으로 전달한다
- covered=false: 빠졌다 / 일부만 담았다(예: 다섯 항목 중 셋만) / 뜻이 다르거나 모호하다
- 사실이 "운영자에게 넘긴다/확인을 넘긴다"이면, 답변이 운영자(담당자)에게 전달·확인하겠다고 말할 때 담은 것이다
- 사실이 "범위 밖임을 알린다"이면, 답변이 그 문의를 안내하지 않는다는 뜻을 밝힐 때 담은 것이다

[forbid — 말하면 안 되는 내용]
- violated=true: 답변이 그 내용을 주장하거나 안내하거나 그렇게 받아들여지게 말한다
- violated=false: 답변이 그 내용을 말하지 않았거나, 부정하는 맥락에서만 언급한다("보상하지 않습니다"는 "보상한다"의 위반이 아니다)

[evidence]
- 판정의 근거가 된 답변 속 문장을 그대로 짧게 옮긴다. 없으면 "없음"
"""


class FactCheck(BaseModel):
    index: int = Field(description="must 목록의 번호(0부터)")
    covered: bool
    evidence: str = Field(description="근거가 된 답변 문장. 없으면 '없음'")


class ForbidCheck(BaseModel):
    index: int = Field(description="forbid 목록의 번호(0부터)")
    violated: bool
    evidence: str = Field(description="근거가 된 답변 문장. 없으면 '없음'")


class Judgement(BaseModel):
    must: List[FactCheck]
    forbid: List[ForbidCheck]


_chain = None


def judge(item, answer):
    """{"ok", "must": [...], "forbid": [...], "missing": [사실], "violated": [주장]}"""
    global _chain
    if _chain is None:
        _chain = init_chat_model(JUDGE_MODEL, temperature=0, timeout=90, max_retries=2
                                 ).with_structured_output(Judgement)
    criteria = {
        "must": [{"index": i, "fact": m["fact"]} for i, m in enumerate(item["must"])],
        "forbid": [{"index": i, "claim": f["claim"]} for i, f in enumerate(item["forbid"])],
    }
    human = (f"[이용자 문의]\n{item['query']}\n\n[답변]\n{answer}\n\n"
             f"[채점 기준]\n{json.dumps(criteria, ensure_ascii=False, indent=1)}\n\n"
             "must 와 forbid 의 모든 항목을 번호마다 하나씩 판정하라.")
    j = _chain.invoke([("system", JUDGE_RULES), ("human", human)])

    must = {c.index: c for c in j.must}
    forbid = {c.index: c for c in j.forbid}
    # 채점기가 항목을 빠뜨리면 통과로 치지 않는다 — 조용히 통과되는 것이 가장 위험하다
    missing = [m["fact"] for i, m in enumerate(item["must"]) if not (i in must and must[i].covered)]
    violated = [f["claim"] for i, f in enumerate(item["forbid"]) if i not in forbid or forbid[i].violated]
    return {
        "ok": not missing and not violated,
        "missing": missing,
        "violated": violated,
        "must": [c.model_dump() for c in j.must],
        "forbid": [c.model_dump() for c in j.forbid],
    }
