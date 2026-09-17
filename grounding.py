# -*- coding: utf-8 -*-
"""의미 수준 근거 검증. 답변 문장마다 조회한 조항에 뒷받침되는지 LLM 이 판정한다.

guardrail.py(규칙)는 숫자·연락처·조항 번호만 대조해서 두 가지를 못 잡는다.
- 숫자 없는 지어낸 사실 ("보증보험으로 보호됩니다")
- 조항을 안 읽고 도구 설명 문구를 근거처럼 쓴 답 (실험 6, E-008)

채점기(judge.py)와 다른 점: 정답(must·forbid)을 모른다. 실행 중에 조회한 조항만 보고 판정하므로
평가셋 없이 운영 중에도 돌릴 수 있다.
"""
import os
from typing import List, Literal

from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field

from config import ANSWER_MODEL

GROUNDING_MODEL = os.environ.get("RENTAL_GROUNDING_MODEL", ANSWER_MODEL)

RULES = """너는 고객 응대 답변의 근거 검사자다. 답변을 문장 단위로 나누고, 각 문장이 [조회한 조항]에 뒷받침되는지 판정한다.

[판정]
- supported: 조항에 같은 뜻의 내용이 있다. 표현이 달라도 뜻이 같으면 supported
- procedural: 서비스 규칙에 대한 사실 주장이 아닌 문장 — 인사, 사과, 공감, 되묻기, "운영자에게 전달해 확인드리겠습니다" 같은 넘김 안내,
  "안내 자료에 없습니다"처럼 조항에 그 내용이 없다고 말하는 문장, 이용자에게 조항 내용을 하라고 권하는 문장,
  응대하는 쪽 자신의 권한·한계 설명("제가 직접 조회할 수 없습니다", "운영자 확인이 필요합니다")
- user_fact: 이용자가 문의에서 한 말을 되풀이한 것
- unsupported: 사실을 주장하는데 조항에 그 내용이 없거나 조항과 다르다

[주의]
- 네가 아는 일반 지식·법률·다른 서비스 관행으로 뒷받침하지 않는다. 오직 [조회한 조항]만 본다
- 조항에서 논리적으로 바로 따라 나오는 결론은 supported
  - "열람 항목은 A·B·C뿐" → "D는 볼 수 없다"
  - "X는 이용자가 직접 확인할 책임이 있다" → "회사가 X를 대신 확인해 주지 않는다"
- 한 문장에 여러 주장이 있으면 하나라도 조항과 다르거나 없으면 unsupported (예: 조항은 "피신고인 신원 비공개"인데 "신고자와 피신고인 신원 비공개")
- 조항이 "할 수 있다"인데 답변이 "반드시 한다"처럼 강도를 바꾸면 unsupported
- 조회한 조항이 없으면 사실 주장 문장은 모두 unsupported
"""


class SentenceCheck(BaseModel):
    sentence: str = Field(description="답변 문장 원문")
    verdict: Literal["supported", "procedural", "user_fact", "unsupported"]
    basis: str = Field(description="supported 면 근거 조항 id(예: 약관 7조), unsupported 면 무엇이 조항에 없는지 한 줄")


class Grounding(BaseModel):
    sentences: List[SentenceCheck]


_chain = None


def check_grounding(answer, question, sections):
    """{"ok", "unsupported": [{"sentence", "basis"}], "sentences": [...]}"""
    global _chain
    if _chain is None:
        _chain = init_chat_model(GROUNDING_MODEL, temperature=0, timeout=90, max_retries=2
                                 ).with_structured_output(Grounding)
    clauses = "\n\n".join(f"[{s['id']} {s['title']}]\n{s['text']}" for s in sections) or "(없음)"
    human = f"[이용자 문의]\n{question}\n\n[답변]\n{answer}\n\n[조회한 조항]\n{clauses}"
    g = _chain.invoke([("system", RULES), ("human", human)])
    bad = [{"sentence": s.sentence, "basis": s.basis} for s in g.sentences if s.verdict == "unsupported"]
    return {"ok": not bad, "unsupported": bad, "sentences": [s.model_dump() for s in g.sentences]}
