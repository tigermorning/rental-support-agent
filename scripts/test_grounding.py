"""의미 수준 검증기를 파이프라인에 붙이기 전에 저장된 답변으로 시험한다. API 호출 있음.

사용법: python scripts/test_grounding.py [--run 06-account-description-rep1 ...]

세 묶음을 판정한다.
1. 모범 답안 (넘기기·답하기 문항) — 전부 통과해야 한다. 걸리면 오탐
2. forbid 내용을 끼운 답안 (data/judge_controls.json 의 add_forbid) — 걸려야 한다
   단, 범위 밖 문항은 조회 조항이 없어 모든 사실 주장이 걸리므로 따로 센다
3. 실제 실행 답변 (runs/*.json) — 무엇이 걸리는지 사람이 읽는다. 특히 E-008
"""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from config import DATA, WORKERS  # noqa: E402
from context import TOOL_SECTIONS, sections_for_tool  # noqa: E402
from grounding import check_grounding  # noqa: E402


def sections_of(tools):
    out, seen = [], set()
    for t in tools:
        if t in TOOL_SECTIONS:
            for s in sections_for_tool(t):
                if s["id"] not in seen:
                    seen.add(s["id"])
                    out.append(s)
    return out


def pmap(fn, xs):
    with ThreadPoolExecutor(WORKERS) as ex:
        return list(ex.map(fn, xs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", nargs="*", default=["06-account-description-rep1", "06-account-description-rep2"])
    args = ap.parse_args()

    items = {it["id"]: it for f in ("fewshot", "eval")
             for it in json.loads((DATA / f"goldenset_{f}.json").read_text(encoding="utf-8"))["items"]}
    controls = json.loads((DATA / "judge_controls.json").read_text(encoding="utf-8"))["controls"]

    cases = []
    for it in items.values():
        if it["action"] != "OUT_OF_SCOPE":
            cases.append(("reference", it["id"], it["reference"], it["query"], sections_of(it["expected_tools"])))
    for c in controls:
        it = items[c["id"]]
        if c["kind"] == "add_forbid" and it["action"] != "OUT_OF_SCOPE":
            cases.append(("add_forbid", c["id"], c["answer"], it["query"], sections_of(it["expected_tools"])))
    for run in args.run:
        for r in json.loads((ROOT / "runs" / f"{run}.json").read_text(encoding="utf-8"))["results"]:
            o = r["out"]
            if o["action"] == "OUT_OF_SCOPE" or not o["answer"]:
                continue
            cases.append((f"run:{run}", r["id"], o["answer"], items[r["id"]]["query"], sections_of(o["tools"])))

    results = pmap(lambda c: check_grounding(c[2], c[3], c[4]), cases)

    groups = {}
    for (kind, qid, ans, q, secs), res in zip(cases, results):
        groups.setdefault(kind, []).append((qid, ans, res))

    out = {}
    for kind, rows in groups.items():
        flagged = [r for r in rows if not r[2]["ok"]]
        print(f"\n== {kind}: {len(flagged)}/{len(rows)} 걸림")
        for qid, ans, res in flagged:
            for u in res["unsupported"]:
                print(f"  {qid}  「{u['sentence'][:70]}」 — {u['basis'][:60]}")
        out[kind] = [{"id": q, "answer": a, "result": r} for q, a, r in rows]

    path = ROOT / "runs" / "grounding-offline.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n저장: {path}")


if __name__ == "__main__":
    main()
