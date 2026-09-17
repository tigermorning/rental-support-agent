# -*- coding: utf-8 -*-
"""데모 화면.  `streamlit run app.py`

문의 탭: 답변과 함께 판정 라우트·확신도, 호출한 도구, 근거로 쓴 조항 원문, 검증 결과를 보여 준다.
평가 결과 탭: runs/ 에 저장된 최종 측정 결과를 API 호출 없이 보여 준다.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from config import ANSWER_MODEL, CONF_THRESHOLD, MODEL, ROUTES  # noqa: E402
from context import ESCALATE_TOOL, ROUTE_TOOLS  # noqa: E402

FINAL_RUNS = ["06-account-description-rep1", "06-account-description-rep2"]

ROUTE_LABELS = {
    "SCOPE": "서비스 성격·거래 책임",
    "ACCOUNT_PRIVACY": "계정·개인정보",
    "LISTING": "매물 등록",
    "INTERVIEW": "방문·인터뷰",
    "REPORT": "신고·제재",
    "OTHER": "범위 밖",
}
ACTION_VIEW = {
    "ANSWER": ("조항 근거로 답변", "green"),
    "ESCALATE": ("운영자에게 넘김", "orange"),
    "OUT_OF_SCOPE": ("범위 밖 안내", "gray"),
}
TOOL_LABELS = {
    "get_service_scope": "서비스 성격",
    "get_liability_disputes": "책임·분쟁",
    "get_account_rules": "계정 규칙",
    "get_data_handling": "수집·보유·파기",
    "get_privacy_safeguards": "공개 범위·보호조치",
    "get_listing_rules": "매물 등록 기준",
    "get_tenant_info_scope": "임차인 정보 범위",
    "get_rejection_and_conduct": "거절 사유·면담",
    "get_prohibited_acts": "차별금지·금지행위",
    "get_report_process": "신고 절차",
    ESCALATE_TOOL: "운영자에게 넘기기",
}

st.set_page_config(page_title="직거래 문의 응대 에이전트", page_icon="🏠", layout="wide")


@st.cache_resource(show_spinner=False)
def load_agent():
    from agent import run
    return run


@st.cache_data(show_spinner=False)
def load_examples():
    items = json.loads((ROOT / "data" / "goldenset_fewshot.json").read_text(encoding="utf-8"))["items"]
    return [(it["route"], it["query"]) for it in items]


def _bigrams(text):
    t = "".join(ch for ch in text if ch.isalnum())
    return {t[i:i + 2] for i in range(len(t) - 1)}


def overlap(answer, section_text):
    """답변 글자 bigram 중 조항 원문에도 있는 비율. 어느 조항이 답에 쓰였는지 보여 주는 참고값."""
    a = _bigrams(answer or "")
    return len(a & _bigrams(section_text)) / max(1, len(a))


def tool_badge(name):
    color = "orange" if name == ESCALATE_TOOL else "blue"
    return f":{color}-badge[{TOOL_LABELS.get(name, name)}]"


def render_result(q, out):
    action_text, action_color = ACTION_VIEW.get(out["action"], (out["action"], "gray"))

    st.markdown(f"#### 문의\n{q}")
    with st.container(border=True):
        st.markdown(f":{action_color}-badge[{action_text}]")
        st.markdown(out["answer"])

    st.markdown("#### 처리 과정")
    c1, c2, c3, c4 = st.columns(4)
    conf = out.get("confidence") or 0.0
    with c1:
        st.markdown("**① 분류**")
        st.markdown(f"{ROUTE_LABELS.get(out.get('route'), out.get('route'))}  \n`{out.get('route')}`")
        st.progress(min(max(conf, 0.0), 1.0), text=f"확신도 {conf:.2f}")
        if out.get("reason"):
            st.caption(out["reason"])
    with c2:
        st.markdown("**② 판정**")
        decision = out.get("decision")
        if decision == "HANDLE":
            st.markdown(":green-badge[처리]")
            st.caption(f"확신도 {CONF_THRESHOLD} 이상, 서비스 범위 안")
        elif decision == "ESCALATE":
            st.markdown(":orange-badge[넘김]")
            st.caption(f"확신도가 {CONF_THRESHOLD} 미만이라 답변 생성 전에 넘김")
        else:
            st.markdown(":gray-badge[범위 밖]")
            st.caption("근거 문서와 무관한 문의")
    with c3:
        st.markdown("**③ 근거 조회**")
        if out.get("tools"):
            st.markdown(" ".join(tool_badge(t) for t in out["tools"]))
        else:
            st.caption("호출 없음")
        allowed = ROUTE_TOOLS.get(out.get("route"), [])
        if allowed:
            st.caption("이 라우트에서 쓸 수 있는 도구: " + ", ".join(TOOL_LABELS[t] for t in allowed))
    with c4:
        st.markdown("**④ 검증**")
        v = out.get("verify")
        if v is None:
            st.caption("모델 답변이 없어 검증 생략")
        elif v["ok"]:
            st.markdown(":green-badge[통과]")
        else:
            st.markdown(":red-badge[실패 → 넘김]")
        if out.get("attempts", 0) > 1:
            st.caption(f"검증에 걸려 {out['attempts']}번 생성")

    sections = out.get("sections") or []
    st.markdown(f"#### 조회한 조항 ({len(sections)}개)")
    if not sections:
        st.caption("조회한 조항 없음")
    else:
        st.caption("도구는 조항 묶음을 통째로 돌려준다. 답변 문장과 글자가 많이 겹치는 조항부터 보여 준다 — "
                   "'답변과 겹침'은 참고 표시이고 채점·검증에는 쓰지 않는다.")
    scored = sorted(((overlap(out["answer"], s["text"]), s) for s in sections), key=lambda x: -x[0])
    for score, s in scored:
        used = score >= 0.3   # 저장된 답변으로 맞춘 값. 참고 표시라 엄밀하지 않다
        label = f"{s['id']} — {s['title']}" + ("  ·  답변과 겹침" if used else "")
        with st.expander(label, expanded=used and score == scored[0][0]):
            st.markdown(s["text"])

    history = out.get("history") or []
    if history:
        st.markdown("#### 검증 기록")
        for i, h in enumerate(history, 1):
            ok = h["verify"]["ok"]
            with st.expander(f"{i}번째 답변 — {'통과' if ok else '검증 실패'}", expanded=not ok):
                st.markdown(h["answer"])
                st.caption("호출 도구: " + (", ".join(TOOL_LABELS.get(t, t) for t in h["tools"]) or "없음"))
                for vio in h["verify"]["violations"]:
                    st.error(f"{vio['type']}: {vio['detail']}")
                if ok:
                    st.success("조회한 조항 밖의 숫자·연락처·조항 인용 없음")


def ask_tab():
    with st.sidebar:
        st.header("예시 문의")
        st.caption("프롬프트 예시용 문항입니다. 점수를 재는 평가용 문항은 넣지 않았습니다.")
        for route, q in load_examples():
            if st.button(q, key=f"ex-{q}", width="stretch", help=ROUTE_LABELS[route]):
                st.session_state.pending = q
        st.divider()
        st.caption(f"분류 모델 `{MODEL}` · 답변 모델 `{ANSWER_MODEL}`")

    typed = st.chat_input("직거래 서비스 이용에 대해 물어보세요. 예: 확정 전에 집주인이 제 전화번호를 볼 수 있나요?")
    q = typed or st.session_state.pop("pending", None)
    if q:
        with st.status("처리 중…", expanded=False) as status:
            status.update(label="분류 → 판정 → 근거 조회 → 답변 → 검증")
            out = load_agent()(q)
            status.update(label="완료", state="complete")
        st.session_state.setdefault("log", []).insert(0, (q, out))

    log = st.session_state.get("log", [])
    if not log:
        st.info("왼쪽 예시를 누르거나 아래 입력창에 문의를 적어 보세요.")
        return
    render_result(*log[0])
    if len(log) > 1:
        st.divider()
        st.markdown("#### 이전 문의")
        # 펼침 안에 펼침을 둘 수 없어(Streamlit 제약) 이전 문의는 요약만 보여 준다
        for pq, pout in log[1:]:
            text, color = ACTION_VIEW.get(pout["action"], (pout["action"], "gray"))
            with st.container(border=True):
                st.markdown(f"**{pq}**  \n:{color}-badge[{text}] `{pout.get('route')}` "
                            + " ".join(tool_badge(t) for t in pout.get("tools", [])))
                st.markdown(pout["answer"])


@st.cache_data(show_spinner=False)
def load_run(name):
    return json.loads((ROOT / "runs" / f"{name}.json").read_text(encoding="utf-8"))


def eval_tab():
    runs = [load_run(n) for n in FINAL_RUNS]
    items = {it["id"]: it for it in json.loads(
        (ROOT / "data" / "goldenset_eval.json").read_text(encoding="utf-8"))["items"]}

    st.markdown("#### 최종 버전 측정 결과")
    st.caption("평가용 42건을 같은 코드로 두 번 잰 값. LLM 호출이라 실행마다 조금씩 다르다. "
               "기록 전체는 `runs/LAB.md`.")
    cols = st.columns(4)
    metrics = [("분류 정확도", lambda s: s["router"]["acc"], "{:.3f}"),
               ("도구 호출 적절성", lambda s: s["answers"]["tool"], "{:.1%}"),
               ("답변 적절성", lambda s: s["answers"]["answer"], "{:.1%}"),
               ("둘 다 통과", lambda s: s["answers"]["both"], "{:.1%}")]
    for col, (label, get, fmt) in zip(cols, metrics):
        a, b = (get(r["summary"]) for r in runs)
        col.metric(label, f"{fmt.format(a)} / {fmt.format(b)}")

    st.markdown("#### 분류 혼동 행렬 (1회차) — 행=정답, 열=예측")
    y = [items[r["id"]]["route"] for r in runs[0]["results"]]
    p = [r["out"]["route"] for r in runs[0]["results"]]
    cm = pd.crosstab(pd.Categorical(y, ROUTES), pd.Categorical(p, ROUTES), dropna=False)
    cm.index.name, cm.columns.name = None, None
    st.dataframe(cm, width="stretch")

    st.markdown("#### 한 번이라도 실패한 문항")
    by_run = [{r["id"]: r for r in run["results"]} for run in runs]
    rows = []
    for qid, it in items.items():
        marks = []
        for d in by_run:
            s = d[qid]["score"]
            marks.append(("T" if not s["tool_ok"] else "") + ("A" if not s["judge"]["ok"] else "") or "통과")
        if any(m != "통과" for m in marks):
            last = by_run[0][qid] if marks[0] != "통과" else by_run[1][qid]
            rows.append({
                "문항": qid, "라우트": it["route"], "기대 행동": it["action"],
                "1회차": marks[0], "2회차": marks[1], "문의": it["query"],
                "기대 도구": ", ".join(it["expected_tools"]),
                "실제 도구": ", ".join(last["out"]["tools"]),
                "빠진 사실": " / ".join(last["score"]["judge"]["missing"]),
            })
    st.caption("T = 도구 호출 실패, A = 답변 실패")
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


st.title("🏠 직거래 임대 플랫폼 문의 응대 에이전트")
st.caption("이용약관 · 개인정보처리방침 · 차별금지 가이드라인 조항만 근거로 답합니다. "
           "근거가 없거나 본인 건 확인이 필요하면 운영자에게 넘깁니다.")
tab_ask, tab_eval = st.tabs(["문의하기", "평가 결과"])
with tab_ask:
    ask_tab()
with tab_eval:
    eval_tab()
