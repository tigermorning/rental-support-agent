# -*- coding: utf-8 -*-
"""답변에 근거 밖 내용이 섞였는지 기계적으로 검사한다.

허용 출처 = 이번에 조회한 조항 원문 + 이용자 문의 원문.
검사 항목
- 출처 불명 숫자: 답변의 숫자가 허용 출처에 없음 (기간·건수·금액·요율을 지어내는 경우)
- 출처 불명 연락처: 이메일·URL·전화번호가 허용 출처에 없음
- 조회하지 않은 조항 인용: "약관 9조"처럼 인용했는데 조회 결과에 그 조항이 없고 원문에서 언급도 안 됨
- 근거 없는 답변: 조회도 넘김도 없이 답함
- 넘김 약속 불이행: "운영자에게 전달하겠다"고 썼는데 escalate_to_operator 를 안 부름

숫자 아닌 사실(예: "보증보험으로 보호됩니다")은 못 잡는다. 그건 채점기의 forbid 가 잰다.
"""
import re

KOR_NUM = {"한": 1, "하나": 1, "두": 2, "둘": 2, "세": 3, "셋": 3, "네": 4, "넷": 4, "다섯": 5,
           "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10}
# "한 번 더"처럼 수량이 아닌 말이 걸리지 않게 수량 단위 앞의 고유어 수사만 바꾼다
# "한 건씩"처럼 ~씩 붙은 말은 수량이 아니라 차례라서 뺀다
KOR_NUM_RE = re.compile(r"(한|하나|두|둘|세|셋|네|넷|다섯|여섯|일곱|여덟|아홉|열)\s*(가지|개|명|건|곳)(?!\s*씩)")
UNITS = r"영업일|개월|시간|천만원|만원|억원|억|원|건|일|년|주|분|%|퍼센트|배|명|개|가지|회|번|장|세|곳|차"
# 숫자는 단위와 한 쌍으로 대조한다. 숫자만 보면 "제3조"의 3 때문에 "신고 3건"이 통과된다
NUM_UNIT_RE = re.compile(rf"(\d+)\s*({UNITS})")
LIST_MARKER_RE = re.compile(r"^\s*\d+[.)]\s", re.M)
CONTACT_RE = re.compile(
    r"[\w.+-]+@[\w-]+\.[\w.]+"                 # 이메일
    r"|https?://\S+|www\.\S+|\b[\w-]+\.(?:go|or|co)\.kr\b"   # URL·도메인
    r"|\b\d{2,4}-\d{3,4}(?:-\d{4})?\b"          # 전화번호
)
# "운영자에게 전달하겠다"처럼 넘긴다고 말하는 표현. 말만 하고 escalate_to_operator 를 안 부르면 실제로는 안 넘어간다
HANDOFF_RE = re.compile(r"(운영자|운영팀|담당자|상담원)[^.?!\n]{0,12}(전달|연결|넘기|넘겨|문의드리|요청드리|확인드리|확인해 드리|확인 후)")
CITE_RE = re.compile(r"(약관|이용약관|처리방침|개인정보처리방침|가이드라인)\s*(?:제\s*)?(\d+)\s*(조|항)")
CITE_LABEL = {"약관": "약관", "이용약관": "약관", "처리방침": "처리방침",
              "개인정보처리방침": "처리방침", "가이드라인": "가이드라인"}


def _normalize(text):
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    return KOR_NUM_RE.sub(lambda m: f"{KOR_NUM[m.group(1)]}{m.group(2)}", text)


def _quantities(text):
    """(단위 붙은 수량 집합, 단위 없는 숫자 집합)"""
    text = _normalize(text)
    with_unit = {f"{n}{u}" for n, u in NUM_UNIT_RE.findall(text)}
    bare = set(re.findall(r"\d+", NUM_UNIT_RE.sub(" ", text)))
    return with_unit, bare


def _allowed(sources):
    units, nums = set(), set()
    for t in sources:
        u, _ = _quantities(t)
        units |= u
        nums |= set(re.findall(r"\d+", _normalize(t)))
    return units, nums


def verify(answer, question, sections, called_tools, escalated):
    """검증 결과 {"ok", "violations"}. violations 는 [{"type", "detail"}]."""
    violations = []
    sources = [question] + [f"{s['id']} {s['title']}\n{s['text']}" for s in sections]
    joined = "\n".join(sources)

    if not sections and not escalated:
        violations.append({"type": "근거 없는 답변", "detail": "조항 조회도 넘김도 없이 답했다"})

    if not escalated and (m := HANDOFF_RE.search(answer or "")):
        violations.append({"type": "넘김 약속 불이행", "detail": m.group(0)})

    body = LIST_MARKER_RE.sub("", answer or "")
    # 조항 인용은 따로 본다. 인용 숫자가 숫자 검사에 섞이지 않게 먼저 떼어 둔다
    cited = [(CITE_LABEL[m.group(1)], m.group(2), m.group(3)) for m in CITE_RE.finditer(body)]
    body_wo_cite = CITE_RE.sub("", body)

    retrieved_ids = {s["id"] for s in sections}
    for label, n, unit in cited:
        sid = f"{label} {n}{unit}"
        mentioned = re.search(rf"제\s*{n}\s*{unit}|{n}\s*{unit}", joined)
        if sid not in retrieved_ids and not mentioned:
            violations.append({"type": "조회하지 않은 조항 인용", "detail": sid})

    contacts = [c for c in CONTACT_RE.findall(body_wo_cite) if c not in joined]
    if contacts:
        violations.append({"type": "출처 불명 연락처", "detail": contacts})

    body_wo_contacts = CONTACT_RE.sub("", body_wo_cite)
    units, bare = _quantities(body_wo_contacts)
    ok_units, ok_nums = _allowed(sources)
    unknown = sorted(units - ok_units) + sorted(bare - ok_nums, key=int)
    if unknown:
        violations.append({"type": "출처 불명 숫자", "detail": unknown})

    return {"ok": not violations, "violations": violations}


def feedback_text(result):
    lines = []
    for v in result["violations"]:
        if v["type"] == "출처 불명 숫자":
            lines.append(f"- 조회한 조항에 없는 숫자 {v['detail']} 를 썼다. 조항에 없는 숫자는 빼고, 없는 사실이면 운영자에게 넘긴다")
        elif v["type"] == "출처 불명 연락처":
            lines.append(f"- 조회한 조항에 없는 연락처 {v['detail']} 를 썼다. 연락처를 지어내지 않는다")
        elif v["type"] == "넘김 약속 불이행":
            lines.append(f"- '{v['detail']}'라고 썼지만 escalate_to_operator 를 부르지 않았다. "
                         "넘길 거면 도구를 부르고, 조항으로 답이 끝나면 그 문장을 뺀다")
        elif v["type"] == "조회하지 않은 조항 인용":
            lines.append(f"- 조회하지 않은 {v['detail']} 를 인용했다. 조회한 조항만 인용한다")
        else:
            lines.append("- 조항을 조회하지 않고 답했다. 필요한 도구를 불러 조항을 확인한 뒤 답한다")
    return "\n".join(lines)
