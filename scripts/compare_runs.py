"""여러 실행 결과를 문항별로 나란히 본다. 사용법: python scripts/compare_runs.py 01-baseline 01-baseline-rep2 02-...

칸 표시: . 통과 / T 도구 실패 / A 답변 실패 / TA 둘 다. 한 번이라도 실패한 문항만 출력한다.
점수 합계가 같아도 문항이 바뀌었을 수 있다 — 흔들림과 개선을 구분하려면 이 표를 본다.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")


def mark(r):
    s = r["score"]
    return ("T" if not s["tool_ok"] else "") + ("A" if not s["judge"]["ok"] else "") or "."


def main():
    names = sys.argv[1:]
    runs = [{r["id"]: r for r in json.loads((ROOT / "runs" / f"{n}.json").read_text(encoding="utf-8"))["results"]}
            for n in names]
    width = max(len(n) for n in names)
    for i, n in enumerate(names):
        s = json.loads((ROOT / "runs" / f"{n}.json").read_text(encoding="utf-8"))["summary"]
        print(f"[{i}] {n:<{width}}  분류 {s['router']['acc']:.3f}  도구 {s['answers']['tool']:.1%}"
              f"  답변 {s['answers']['answer']:.1%}  둘 다 {s['answers']['both']:.1%}")
    print("\nid     " + "  ".join(f"[{i}]" for i in range(len(names))))
    for qid in sorted(runs[0]):
        row = [mark(r[qid]) if qid in r else "-" for r in runs]
        if any(m != "." for m in row):
            print(f"{qid}  " + "  ".join(f"{m:<3}" for m in row))


if __name__ == "__main__":
    main()
