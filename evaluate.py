# -*- coding: utf-8 -*-
"""지표를 한 번에 잰다.  `python evaluate.py`

    ① 분류       정확도 · macro F1 · 혼동 행렬 (classify 가 고른 라우트 vs 정답 라우트)
    ② 도구 호출   호출한 도구 집합 == 기대 도구 집합 이면 1점
    ③ 답변       must 사실 전부 포함 + forbid 위반 0 이면 1점 (judge.py)
    + 행동        ANSWER / ESCALATE / OUT_OF_SCOPE 일치율 (참고 지표)

옵션
    --split eval|fewshot   기본 eval. fewshot 은 프롬프트에 들어간 예시라 점수가 부풀어 있다
    --only router          분류만 (에이전트·채점기 안 부름)
    --tag 이름             결과를 runs/<tag>.json 으로 저장
    --rescore runs/x.json  에이전트를 다시 돌리지 않고 저장된 답변을 다시 채점
    --validate             채점기 자체 검증 (모범 답안·오답 변형)
    --ids E-001,E-002      일부 문항만
"""
import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

from config import CONF_THRESHOLD, DATA, ROOT, ROUTES, WORKERS

sys.stdout.reconfigure(encoding="utf-8")
RUNS = ROOT / "runs"


def pmap(fn, items):
    with ThreadPoolExecutor(WORKERS) as ex:
        return list(ex.map(fn, items))


def load_items(split, ids=None):
    items = json.loads((DATA / f"goldenset_{split}.json").read_text(encoding="utf-8"))["items"]
    assert all(it["split"] == split for it in items)
    if ids:
        items = [it for it in items if it["id"] in ids]
    return items


# ───────────────────────── 실행 ─────────────────────────
def run_router(items):
    from router import classify, gate

    def one(it):
        r = classify({"question": it["query"]})
        return {**r, **gate(r)}
    return pmap(one, items)


def run_agent(items):
    from agent import run

    def one(it):
        out = run(it["query"])
        return {
            "route": out.get("route"), "confidence": out.get("confidence"), "reason": out.get("reason"),
            "decision": out.get("decision"), "action": out.get("action"), "tools": out.get("tools", []),
            "sections": [s["id"] for s in out.get("sections", [])], "answer": out.get("answer"),
            "verify": out.get("verify"), "attempts": out.get("attempts", 0),
            "history": out.get("history", []),
        }
    return pmap(one, items)


# ───────────────────────── ① 분류 ─────────────────────────
def report_router(items, outs):
    y = [it["route"] for it in items]
    p = [o["route"] for o in outs]
    acc = accuracy_score(y, p)
    f1 = f1_score(y, p, labels=ROUTES, average="macro", zero_division=0)
    print("── ① 분류 ─────────────────────────────")
    print(f"n={len(items)}  정확도 {acc:.3f}  macro F1 {f1:.3f}")
    cm = confusion_matrix(y, p, labels=ROUTES)
    short = {"ACCOUNT_PRIVACY": "ACCOUNT", "INTERVIEW": "INTERV"}
    cols = [short.get(r, r) for r in ROUTES]
    print("\n[혼동 행렬] 행=정답, 열=예측")
    print(pd.DataFrame(cm, index=ROUTES, columns=cols).to_string())
    miss = [(it, o) for it, o in zip(items, outs) if it["route"] != o["route"]]
    print(f"\n[오분류 {len(miss)}건]")
    for it, o in miss:
        print(f"  {it['id']} [{it['route']} → {o['route']}] conf={o['confidence']:.2f}  {it['query'][:50]}")
        print(f"      이유: {o.get('reason', '')[:80]}")
    low = [(it, o) for it, o in zip(items, outs) if o["confidence"] < CONF_THRESHOLD]
    print(f"\n[확신도 {CONF_THRESHOLD} 미만 → gate 가 넘김] {len(low)}건"
          + "".join(f"\n  {it['id']} conf={o['confidence']:.2f} 정답={it['route']} 예측={o['route']}"
                    for it, o in low))
    return {"acc": acc, "macro_f1": f1, "n": len(items), "misrouted": [it["id"] for it, _ in miss]}


# ───────────────────────── ②③ 도구·답변 ─────────────────────────
def score(items, outs):
    from judge import judge

    def one(pair):
        it, o = pair
        tool_ok = set(o["tools"]) == set(it["expected_tools"])
        return {"tool_ok": tool_ok, "judge": judge(it, o["answer"] or "")}
    return pmap(one, list(zip(items, outs)))


def tool_diff(expected, called):
    e, c = set(expected), set(called)
    parts = []
    if e - c:
        parts.append(f"누락 {sorted(e - c)}")
    if c - e:
        parts.append(f"과잉 {sorted(c - e)}")
    return " · ".join(parts)


def report_answers(items, outs, scores):
    n = len(items)
    tool = sum(s["tool_ok"] for s in scores)
    ans = sum(s["judge"]["ok"] for s in scores)
    both = sum(s["tool_ok"] and s["judge"]["ok"] for s in scores)
    act = sum(it["action"] == o["action"] for it, o in zip(items, outs))
    print("\n── ②③ 도구 호출 · 답변 ─────────────────────")
    print(f"도구 호출 적절성  {tool}/{n} = {tool / n:.1%}")
    print(f"답변 적절성      {ans}/{n} = {ans / n:.1%}")
    print(f"둘 다 통과       {both}/{n} = {both / n:.1%}")
    print(f"행동 일치(참고)  {act}/{n} = {act / n:.1%}")

    df = pd.DataFrame([{"route": it["route"], "action": it["action"], "tool": s["tool_ok"],
                        "answer": s["judge"]["ok"]} for it, s in zip(items, scores)])
    print("\n[라우트별]")
    print(df.groupby("route")[["tool", "answer"]].mean().round(2).to_string())
    print("\n[기대 행동별]")
    print(df.groupby("action")[["tool", "answer"]].mean().round(2).to_string())
    print("\n[행동 판정] 행=기대, 열=실제")
    print(pd.crosstab(pd.Series([it["action"] for it in items], name="기대"),
                      pd.Series([o["action"] for o in outs], name="실제")).to_string())

    kinds = Counter()
    for it, o, s in zip(items, outs, scores):
        e, c = set(it["expected_tools"]), set(o["tools"])
        kinds["도구 누락"] += bool(e - c)
        kinds["도구 과잉"] += bool(c - e)
        kinds["must 누락"] += bool(s["judge"]["missing"])
        kinds["forbid 위반"] += bool(s["judge"]["violated"])
        kinds["검증 재시도"] += o["attempts"] > 1
    print("\n[실패 유형 — 문항 수]")
    print("\n".join(f"  {k}: {v}" for k, v in kinds.items() if v) or "  없음")

    print("\n[실패 사례] — 점수보다 여기를 읽는다")
    for it, o, s in zip(items, outs, scores):
        if s["tool_ok"] and s["judge"]["ok"]:
            continue
        print(f"  {it['id']} {it['route']}/{it['action']} → {o['route']}/{o['action']} conf={o['confidence']:.2f}")
        print(f"      문의: {it['query'][:70]}")
        if not s["tool_ok"]:
            print(f"      도구: 기대 {it['expected_tools']} / 실제 {o['tools']}  ({tool_diff(it['expected_tools'], o['tools'])})")
        for m in s["judge"]["missing"]:
            print(f"      must 누락: {m}")
        for f in s["judge"]["violated"]:
            print(f"      forbid 위반: {f}")
        if o.get("verify") and not o["verify"]["ok"]:
            print(f"      검증: {o['verify']['violations']}")
        print(f"      답변: {(o['answer'] or '')[:160]}")
    return {"tool": tool / n, "answer": ans / n, "both": both / n, "action": act / n, "n": n}


# ───────────────────────── 채점기 검증 ─────────────────────────
def validate():
    """모범 답안은 전부 통과, 오답 변형은 전부 실패여야 한다. 어긋난 건은 근거와 함께 출력한다."""
    from judge import judge

    items = load_items("fewshot") + load_items("eval")
    by_id = {it["id"]: it for it in items}
    controls = json.loads((DATA / "judge_controls.json").read_text(encoding="utf-8"))["controls"]

    cases = [("reference", it, it["reference"], True, None) for it in items]
    cases += [(c["kind"], by_id[c["id"]], c["answer"], False, c["target"]) for c in controls]
    results = pmap(lambda c: judge(c[1], c[2]), cases)

    print("── 채점기 검증 ─────────────────────────────")
    rows = []
    for (kind, it, ans, expect_ok, target), r in zip(cases, results):
        # 오답 변형은 "노린 항목"을 잡았는지까지 본다. 다른 이유로 실패하면 우연히 맞은 것이다
        if kind == "drop_must":
            hit = target in r["missing"]
        elif kind == "add_forbid":
            hit = target in r["violated"]
        else:
            hit = r["ok"]
        rows.append({"kind": kind, "hit": hit})
        if not hit:
            print(f"\n  ✗ {kind} {it['id']} — 기대 {'통과' if expect_ok else '실패'}")
            if target:
                print(f"      노린 항목: {target}")
            print(f"      판정: missing={r['missing']} violated={r['violated']}")
            print(f"      답변: {ans[:200]}")
    df = pd.DataFrame(rows)
    print("\n[요약] 기대대로 판정한 비율")
    labels = {"reference": "모범 답안 → 통과", "drop_must": "사실 하나 뺌 → 그 사실 누락 판정",
              "add_forbid": "금지 내용 넣음 → 그 항목 위반 판정"}
    for k, g in df.groupby("kind", sort=False):
        print(f"  {labels[k]:<28} {g['hit'].sum()}/{len(g)} = {g['hit'].mean():.1%}")
    return df


# ───────────────────────── 메인 ─────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="eval", choices=["eval", "fewshot"])
    ap.add_argument("--only", choices=["router"])
    ap.add_argument("--tag")
    ap.add_argument("--rescore")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--ids")
    args = ap.parse_args()

    if args.validate:
        validate()
        return

    ids = set(args.ids.split(",")) if args.ids else None
    items = load_items(args.split, ids)

    if args.only == "router":
        report_router(items, run_router(items))
        return

    if args.rescore:
        saved = json.loads(Path(args.rescore).read_text(encoding="utf-8"))
        by_id = {r["id"]: r["out"] for r in saved["results"]}
        items = [it for it in items if it["id"] in by_id]
        outs = [by_id[it["id"]] for it in items]
    else:
        outs = run_agent(items)

    router = report_router(items, outs)
    scores = score(items, outs)
    answers = report_answers(items, outs, scores)

    print("\n══ 요약 ══")
    print(f"  ① 분류       정확도 {router['acc']:.3f} · macro F1 {router['macro_f1']:.3f}")
    print(f"  ② 도구 호출  {answers['tool']:.1%}")
    print(f"  ③ 답변       {answers['answer']:.1%}")
    print(f"  ②③ 둘 다     {answers['both']:.1%}   (행동 일치 {answers['action']:.1%})")

    if args.tag:
        RUNS.mkdir(exist_ok=True)
        path = RUNS / f"{args.tag}.json"
        path.write_text(json.dumps({
            "tag": args.tag, "split": args.split,
            "summary": {"router": router, "answers": answers},
            "results": [{"id": it["id"], "out": o, "score": s} for it, o, s in zip(items, outs, scores)],
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n저장: {path}")


if __name__ == "__main__":
    main()
