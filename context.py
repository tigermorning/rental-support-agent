# -*- coding: utf-8 -*-
"""근거 문서를 조항 단위로 쪼개고, 도구·라우트별로 필요한 조항만 모은다.

문서 전체(약 22k자)를 넣지 않는 이유: 비용·지연도 있지만, 관련 없는 조항이 오답을 끌어온다
(연락처 공개 문의에 처리방침 9항의 빈 연락처가 섞여 "연락처는 추후 기재"라고 답하는 식).

이 파일은 표준 라이브러리만 쓴다. scripts/check_goldenset.py 가 같은 표를 가져다 쓴다.
"""
import re
from pathlib import Path

DOCS = Path(__file__).parent / "docs"

# 파일 → (문서 약칭, 번호 단위)
DOC_FILES = {
    "terms.md": ("약관", "조"),
    "privacy.md": ("처리방침", "항"),
    "non-discrimination.md": ("가이드라인", "항"),
}

# 도구 → 반환하는 조항. docs/MAPPING.md 4장, data/SCHEMA.md 3장과 같은 표다.
TOOL_SECTIONS = {
    "get_service_scope": [("약관", n) for n in (1, 2, 3, 11)],
    "get_liability_disputes": [("약관", 12), ("약관", 13), ("가이드라인", 7)],
    "get_account_rules": [("약관", 4), ("약관", 5), ("처리방침", 7)],
    "get_data_handling": [("처리방침", n) for n in (1, 2, 3, 6)],
    "get_privacy_safeguards": [("처리방침", n) for n in (4, 5, 8, 9, 10, 11, 12)],
    "get_listing_rules": [("약관", 6)],
    "get_tenant_info_scope": [("약관", 7), ("가이드라인", 1), ("가이드라인", 2), ("가이드라인", 3)],
    "get_rejection_and_conduct": [("가이드라인", 4), ("가이드라인", 5)],
    "get_prohibited_acts": [("약관", 8), ("약관", 9)],
    "get_report_process": [("약관", 10), ("가이드라인", 6)],
}

TOOL_DESCRIPTIONS = {
    "get_service_scope": "서비스의 성격(중개가 아님, 하지 않는 일), 용어 정의, 서비스 지역·요금, 서비스 변경·중단 공지",
    "get_liability_disputes": "회사 책임의 범위, 이용자가 직접 확인할 것, 임대차 분쟁 조정, 차별 구제 기관(국가인권위원회)",
    "get_account_rules": "약관 변경 공지, 회원가입 조건·로그인 방식·계정 도용, 탈퇴, 개인정보 열람·정정·삭제 요구 방법",
    "get_data_handling": "개인정보 처리 목적, 수집 항목과 수집하지 않는 정보, 항목별 보유 기간, 파기 절차",
    "get_privacy_safeguards": "임대인·임차인 사이 정보 공개 범위와 제3자 제공, 처리 위탁(서버 위치), 보안 조치, 보호책임자, 유출 시 조치, 구제 기관, 방침 변경",
    "get_listing_rules": "매물 등록 기준(소유·권한 서류, 대리 등록, 조건 기재, 마감, 중복 등록), 주택임대차 신고 의무",
    "get_tenant_info_scope": "임대인이 볼 수 있는 임차인 정보(재정 3항목), 연락처 공개 시점, 서비스가 수집하지 않는 정보, 선정 원칙",
    "get_rejection_and_conduct": "거절 사유 닫힌 목록, 재정정보 사본 보관, 방문·면담에서 지킬 것",
    "get_prohibited_acts": "차별금지 정책(차별 사유 목록), 금지행위(허위매물, 사전 송금 요구, 외부 연락 유도, 괴롭힘 등)",
    "get_report_process": "허위매물·사기·차별 신고 방법, 신고 후 확인·임시 비공개, 제재 종류, 이의 제기, 신고자 보호",
}

# 라우트 → 모델에 붙일 조회 도구. escalate_to_operator 는 모든 라우트에 붙는다.
ROUTE_TOOLS = {
    "SCOPE": ["get_service_scope", "get_liability_disputes", "get_listing_rules"],
    "ACCOUNT_PRIVACY": ["get_account_rules", "get_data_handling", "get_privacy_safeguards"],
    "LISTING": ["get_listing_rules", "get_prohibited_acts"],
    "INTERVIEW": ["get_tenant_info_scope", "get_rejection_and_conduct", "get_privacy_safeguards"],
    "REPORT": ["get_report_process", "get_prohibited_acts", "get_liability_disputes"],
    "OTHER": [],
}

ESCALATE_TOOL = "escalate_to_operator"

HEADING_RE = re.compile(r"^## (?:제\s*(\d+)\s*조|(\d+)\.)\s*(.*)$")


def split_sections(docs_dir: Path = DOCS):
    """docs/*.md 를 '## ' 헤딩 단위로 쪼갠다. 키는 (문서 약칭, 번호). 부칙처럼 번호 없는 섹션은 뺀다."""
    out = {}
    for fname, (label, unit) in DOC_FILES.items():
        current, lines = None, []

        def flush():
            if current:
                out[current[0]] = {
                    "id": f"{label} {current[0][1]}{unit}",
                    "title": current[1],
                    "text": "\n".join(lines).strip(),
                }

        for line in (docs_dir / fname).read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                flush()
                m = HEADING_RE.match(line)
                current = ((label, int(m.group(1) or m.group(2))), line[3:].strip()) if m else None
                lines = []
            elif current and not line.startswith("<!--"):
                lines.append(line)
        flush()
    return out


SECTIONS = split_sections()


def sections_for_tool(tool_name: str):
    return [SECTIONS[k] for k in TOOL_SECTIONS[tool_name]]


def tools_for_route(route: str):
    return ROUTE_TOOLS.get(route, []) + [ESCALATE_TOOL]
