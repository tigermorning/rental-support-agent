# -*- coding: utf-8 -*-
"""한곳에 모아 둔 설정. 여기 값만 바꿔도 동작이 달라진다.

- MODEL          : 라우팅용. 출력이 짧고 호출이 많아 비용 최적화 등급이면 충분하다.
- ANSWER_MODEL   : 답변 생성용. 조항 원문이 붙어 입력이 길고 지켜야 할 조건이 많다.
- CONF_THRESHOLD : 이 값 미만이면 운영자에게 넘긴다. 올리면 안전해지고 자동화율이 떨어진다.
"""
import os
from pathlib import Path

ROOT = Path(__file__).parent
DOCS = ROOT / "docs"
DATA = ROOT / "data"


def _load_dotenv():
    """.env 가 있으면 환경변수로 읽는다. 이미 설정된 값은 덮지 않는다."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

MODEL = os.environ.get("RENTAL_MODEL", "gpt-5.6-luna")
ANSWER_MODEL = os.environ.get("RENTAL_ANSWER_MODEL", "gpt-5.6-terra")

CONF_THRESHOLD = 0.5    # 라우팅 확신도 임계값
MAX_TOOL_TURNS = 5      # 도구 호출 루프 상한
VERIFY_RETRY = 1        # 검증 실패 시 재생성 횟수
WORKERS = 8             # 동시 호출 수. 요청 한도에 걸리면 낮춘다

ROUTES = ["SCOPE", "ACCOUNT_PRIVACY", "LISTING", "INTERVIEW", "REPORT", "OTHER"]
