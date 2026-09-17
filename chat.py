# -*- coding: utf-8 -*-
"""직접 물어본다.  `python chat.py "중개수수료 얼마예요?"`  또는 인자 없이 대화형.

답변 아래에 라우트 · 확신도 · 판정 · 호출 도구 · 조회 조항 · 검증 결과가 찍힌다.
틀린 답이 나오면 이 줄이 분류·조회·생성·검증 중 어디서 틀렸는지 알려 준다.
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")


def show(out):
    conf = out.get("confidence")
    print(f'답변 > {out["answer"]}')
    print(f'  route={out.get("route")} conf={conf:.2f} gate={out.get("decision")} action={out["action"]}')
    print(f'  tools={out.get("tools", [])}')
    print(f'  sections={[s["id"] for s in out.get("sections", [])]}')
    v = out.get("verify")
    print(f'  verify={"-" if v is None else ("통과" if v["ok"] else v["violations"])}'
          f'  attempts={out.get("attempts", 0)}\n')


def main():
    from agent import run
    if len(sys.argv) > 1:
        for q in sys.argv[1:]:
            print(f"문의 > {q}")
            show(run(q))
        return
    print("문의를 입력하세요. 빈 줄이면 끝.\n")
    while q := input("문의 > ").strip():
        show(run(q))


if __name__ == "__main__":
    main()
