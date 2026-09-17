"""평가셋 형식·일관성 검사. 사용법: python scripts/check_goldenset.py [파일 ...]

data/SCHEMA.md 규칙을 기계적으로 확인한다.
- 필드·값 범위
- must.source 조항이 인용문처럼 docs/ 에 실제로 있는지 (섹션 제목 존재 여부)
- expected_tools 가 must.source 조항을 반환하는 도구 집합과 정확히 같은지 (+ ESCALATE 면 escalate_to_operator)
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")

ROUTES = ["SCOPE", "ACCOUNT_PRIVACY", "LISTING", "INTERVIEW", "REPORT", "OTHER"]
ACTIONS = ["ANSWER", "ESCALATE", "OUT_OF_SCOPE"]
ESCALATE = "escalate_to_operator"

# data/SCHEMA.md 3장과 같은 표. (문서, 번호) -> 도구
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
SECTION_TOOL = {sec: tool for tool, secs in TOOL_SECTIONS.items() for sec in secs}
ALL_TOOLS = set(TOOL_SECTIONS) | {ESCALATE}

SOURCE_RE = re.compile(r"(약관|처리방침|가이드라인)\s*(\d+)\s*(?:조|항)")


def sections_in(source: str):
    return [(doc, int(n)) for doc, n in SOURCE_RE.findall(source)]


def check(items):
    errors = []
    ids = Counter(it.get("id") for it in items)
    errors += [f"id 중복: {i}" for i, c in ids.items() if c > 1]

    for it in items:
        iid = it.get("id", "?")
        err = lambda msg: errors.append(f"{iid}: {msg}")  # noqa: E731

        for field in ("id", "split", "query", "route", "action", "expected_tools", "must", "forbid", "reference"):
            if field not in it:
                err(f"필드 없음 {field}")
        if errors and errors[-1].startswith(f"{iid}: 필드 없음"):
            continue

        if it["route"] not in ROUTES:
            err(f"route 값 {it['route']}")
        if it["action"] not in ACTIONS:
            err(f"action 값 {it['action']}")
        tools = set(it["expected_tools"])
        if unknown := tools - ALL_TOOLS:
            err(f"없는 도구 {sorted(unknown)}")
        if not 1 <= len(it["must"]) <= 4:
            err(f"must 개수 {len(it['must'])}")
        if not 1 <= len(it["forbid"]) <= 3:
            err(f"forbid 개수 {len(it['forbid'])}")
        for m in it["must"]:
            if not m.get("fact") or not m.get("source"):
                err(f"must 항목에 fact/source 없음: {m}")
        for f in it["forbid"]:
            if not f.get("claim"):
                err(f"forbid 항목에 claim 없음: {f}")

        # 라우트·행동 조합
        if it["route"] == "OTHER" and it["action"] != "OUT_OF_SCOPE":
            err("OTHER 인데 OUT_OF_SCOPE 아님")
        if it["action"] == "OUT_OF_SCOPE" and (it["route"] != "OTHER" or tools):
            err("OUT_OF_SCOPE 는 OTHER 라우트·도구 없음이어야 함")
        if it["action"] == "ESCALATE" and ESCALATE not in tools:
            err("ESCALATE 인데 escalate_to_operator 없음")
        if it["action"] == "ANSWER" and ESCALATE in tools:
            err("ANSWER 인데 escalate_to_operator 있음")

        # 근거 조항 -> 기대 도구 집합
        needed = set()
        for m in it["must"]:
            for sec in sections_in(m.get("source", "")):
                if sec not in SECTION_TOOL:
                    err(f"어느 도구도 반환하지 않는 조항 {sec[0]} {sec[1]}")
                else:
                    needed.add(SECTION_TOOL[sec])
        lookup = tools - {ESCALATE}
        if it["action"] != "OUT_OF_SCOPE":
            if missing := needed - lookup:
                err(f"must 근거인데 도구에 없음 {sorted(missing)}")
            if extra := lookup - needed:
                err(f"must 근거가 없는 도구 {sorted(extra)}")
        if it["action"] == "ANSWER" and not lookup:
            err("ANSWER 인데 조회 도구 없음")
    return errors


def summarize(items):
    table = Counter((it["route"], it["action"]) for it in items)
    print(f"{'route':<17}" + "".join(f"{a:>14}" for a in ACTIONS) + f"{'합':>6}")
    for r in ROUTES:
        row = [table[(r, a)] for a in ACTIONS]
        print(f"{r:<17}" + "".join(f"{n:>14}" for n in row) + f"{sum(row):>6}")
    print(f"{'합':<17}" + "".join(f"{sum(table[(r, a)] for r in ROUTES):>14}" for a in ACTIONS) + f"{len(items):>6}")


def main():
    files = sys.argv[1:] or sorted(str(p) for p in (ROOT / "data").glob("goldenset*.json"))
    failed = False
    for f in files:
        items = json.loads(Path(f).read_text(encoding="utf-8"))["items"]
        print(f"\n== {Path(f).name} ({len(items)}건)")
        summarize(items)
        errors = check(items)
        for e in errors:
            print("  ✗", e)
        print("  통과" if not errors else f"  오류 {len(errors)}건")
        failed |= bool(errors)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
