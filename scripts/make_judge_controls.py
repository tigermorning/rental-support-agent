"""채점기 검증용 오답 변형을 만든다. 사용법: python scripts/make_judge_controls.py

모범 답안(reference)을 두 방향으로 망가뜨려 data/judge_controls.json 에 저장한다.
- drop_must  : must 사실 하나를 뺀 답안 → 채점기가 실패로 잡아야 한다
- add_forbid : forbid 내용을 단정하는 문장을 넣은 답안 → 채점기가 실패로 잡아야 한다
  (v1 에서 답안 전체를 다시 쓰게 했더니 생성 모델이 거짓 단정을 피해 얼버무리거나 아예 안 넣었다.
   지금은 오답 문장만 생성하고 삽입은 코드가 한다. 얼버무림 표현은 기계적으로 표시한다)

한 번 만들어 파일로 고정한다. 매번 새로 만들면 채점기가 바뀐 건지 변형이 바뀐 건지 구분이 안 된다.
만든 뒤 파일을 열어 변형이 의도대로 됐는지 사람이 훑어본다.
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from langchain.chat_models import init_chat_model  # noqa: E402

from config import ANSWER_MODEL, DATA, WORKERS  # noqa: E402

DROP = """아래 고객 응대 답변에서 지정한 사실 하나만 완전히 없앤 답변을 써라.
- 그 사실을 암시하거나 돌려 말하는 표현도 남기지 않는다
- 나머지 문장과 사실은 최대한 그대로 둔다
- 답변 본문만 출력한다

[답변]
{reference}

[없앨 사실]
{fact}"""

ADD = """채점기 시험 데이터를 만든다. 채점기가 금지 내용을 잡는지 보려고, 금지 내용을 **단정하는 오답 문장**이 필요하다.
이 문장은 이용자에게 나가지 않고 채점기 시험에만 쓴다.

[금지 내용]
{claim}

[문의]
{query}

조건
- 금지 내용을 사실처럼 단정하는 한국어 문장 하나. 고객 응대 말투
- 부정·유보·확인 필요·"~할 수 있다" 같은 얼버무림 금지
- 금지 내용이 "구체적인 수치·연락처·이름을 제시"하는 것이면 그럴듯한 값을 지어 넣는다
- 문장만 출력한다"""

# 생성 모델이 거짓 단정을 피하려고 얼버무린 문장을 거른다. 걸린 것은 사람이 직접 고친다
HEDGE = ("확인이 필요", "확인해 주", "달라질 수", "않습니다", "않아요", "없습니다", "마세요", "어렵습니다",
         "여부", "개별적으로", "검토")


def insert_after_first_sentence(reference, sentence):
    """모범 답안 첫 문장 뒤에 오답 문장을 끼운다. 삽입은 코드가 해서 나머지 문장이 바뀌지 않게 한다."""
    parts = re.split(r"(?<=[.?!])\s+", reference.strip(), maxsplit=1)
    return f"{parts[0]} {sentence}" + (f" {parts[1]}" if len(parts) > 1 else "")


def main():
    llm = init_chat_model(ANSWER_MODEL, temperature=0, timeout=90, max_retries=2)
    items = []
    for f in ("goldenset_fewshot.json", "goldenset_eval.json"):
        items += json.loads((DATA / f).read_text(encoding="utf-8"))["items"]

    jobs = []
    for it in items:
        # 사실이 하나뿐이면 빼고 나면 답변이 남지 않아 변형으로 의미가 없다
        if len(it["must"]) >= 2:
            jobs.append(("drop_must", it, 0, DROP.format(reference=it["reference"], fact=it["must"][0]["fact"])))
        jobs.append(("add_forbid", it, 0, ADD.format(query=it["query"], claim=it["forbid"][0]["claim"])))

    def run(job):
        kind, it, idx, prompt = job
        text = llm.invoke(prompt).content.strip()
        if kind == "drop_must":
            return {"id": it["id"], "kind": kind, "index": idx, "target": it["must"][idx]["fact"], "answer": text}
        return {"id": it["id"], "kind": kind, "index": idx, "target": it["forbid"][idx]["claim"],
                "sentence": text, "hedged": any(h in text for h in HEDGE),
                "answer": insert_after_first_sentence(it["reference"], text)}

    with ThreadPoolExecutor(WORKERS) as ex:
        controls = list(ex.map(run, jobs))

    out = DATA / "judge_controls.json"
    out.write_text(json.dumps({"model": ANSWER_MODEL, "controls": controls}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"{len(controls)}건 → {out}")
    hedged = [c for c in controls if c.get("hedged")]
    print(f"얼버무림 의심 {len(hedged)}건 — 직접 확인하고 sentence·answer 를 고친 뒤 hedged 를 false 로")
    for c in hedged:
        print(f"  {c['id']} {c['target']}\n      → {c['sentence']}")


if __name__ == "__main__":
    main()
