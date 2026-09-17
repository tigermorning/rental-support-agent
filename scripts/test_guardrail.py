"""검증기 오프라인 시험. API 호출 없음. 사용법: python scripts/test_guardrail.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from context import sections_for_tool as s  # noqa: E402
from guardrail import verify  # noqa: E402

# (이름, 조회 조항, 답변, 넘김 여부, 기대 통과 여부, 문의)
CASES = [
    ("신고 3건 지어냄 — 원문 '제3조'의 3에 속으면 안 됨", s("get_report_process"),
     "신고가 3건 누적되면 매물이 자동으로 비공개됩니다.", False, False, "문의"),
    ("고유어 수사도 잡음", s("get_report_process"),
     "신고가 세 건 쌓이면 비공개됩니다.", False, False, "문의"),
    ("정상 답변", s("get_report_process"),
     "신고를 접수하면 사실관계를 확인하며, 확인 전이라도 매물을 임시로 비공개할 수 있습니다.", False, True, "문의"),
    ("원문 '다섯 가지'를 5가지로", s("get_rejection_and_conduct"),
     "거절 사유는 5가지 중에서만 고를 수 있습니다.", False, True, "문의"),
    ("지어낸 이메일", s("get_account_rules"),
     "privacy@jikgeorae.kr 로 요청해 주세요. 10일 이내에 조치합니다.", False, False, "문의"),
    ("원문에 있는 인권위 번호", s("get_liability_disputes"),
     "국가인권위원회(국번없이 1331)에 진정할 수 있습니다.", False, True, "문의"),
    ("조회하지 않은 조항 인용", s("get_report_process"),
     "이용약관 12조에 따라 책임지지 않습니다.", False, False, "문의"),
    ("원문이 언급한 조항 인용", s("get_tenant_info_scope"),
     "요구하면 이용약관 9조 위반으로 제재 대상이 됩니다.", False, True, "문의"),
    ("조회 없이 답변", [], "무료입니다.", False, False, "문의"),
    ("넘기기만", [], "운영자에게 전달했습니다.", True, True, "문의"),
    ("이용자가 말한 숫자 되풀이", s("get_report_process"),
     "3일 전 신고하신 건은 운영자에게 전달했습니다.", True, True, "3일 전에 신고했어요"),
    ("번호 목록 표시는 숫자로 안 봄", s("get_rejection_and_conduct"),
     "1. 일정 불가\n2. 이미 계약 완료", False, True, "문의"),
    ("중개보수율 지어냄", s("get_service_scope"), "중개보수는 0.4%입니다.", False, False, "문의"),
    ("원문 금액·기한", s("get_listing_rules"),
     "보증금 6천만원 초과 또는 월세 30만원 초과면 30일 이내에 신고해야 합니다.", False, True, "문의"),
    ("처리 기간 지어냄", s("get_listing_rules"), "확인은 1~2영업일 걸립니다.", False, False, "문의"),
    ("'한 건씩'은 수량 아님 (실제 오탐)", s("get_service_scope"),
     "신청 목록에서 한 건씩 확인해 결정해 주세요.", False, True, "문의"),
    ("넘긴다고 말하고 도구 안 부름 (E-035 실제 사례)", s("get_report_process"),
     "신고 누적 기준은 안내 자료에 없어 운영자에게 전달해 확인드리겠습니다.", False, False, "문의"),
    ("넘긴다고 말하고 도구 부름", s("get_report_process"),
     "신고 누적 기준은 안내 자료에 없어 운영자에게 전달해 확인드리겠습니다.", True, True, "문의"),
    ("운영자 언급이지만 넘김 약속 아님", s("get_report_process"),
     "회사는 신고를 접수하면 사실관계를 확인합니다.", False, True, "문의"),
    ("원문 72시간", s("get_privacy_safeguards"), "72시간 이내에 신고합니다.", False, True, "문의"),
]


def main():
    bad = 0
    for name, secs, ans, esc, expect, q in CASES:
        r = verify(ans, q, secs, [], esc)
        ok = r["ok"] == expect
        bad += not ok
        print("OK " if ok else "BAD", name, r["violations"] or "")
    print(f"\n{len(CASES) - bad}/{len(CASES)} 기대대로")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
