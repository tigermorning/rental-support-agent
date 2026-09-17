# 직거래 임대 플랫폼 문의 응대 에이전트

- 이용자 문의 한 줄 → 카테고리 판정 → 카테고리별 약관 조항만 조회 → 조항 근거로 답변 → 근거 밖 내용 검증
- 문서에 답이 없거나 본인 건 확인이 필요하면 운영자에게 넘김
- 근거: 이용약관 · 개인정보처리방침 · 차별금지 가이드라인 ([docs/](docs/))
- 설계·측정·회고 전체: **[REPORT.md](REPORT.md)**

## 결과 (평가용 42건, 2회 측정)

| 지표 | 기준선 | 최종 |
|---|---|---|
| 분류 정확도 / macro F1 | 1.000 / 0.976 | 1.000 / 1.000 |
| 도구 호출 적절성 | 83.3% / 85.7% | 92.9% / 92.9% |
| 답변 적절성 | 76.2% / 76.2% | 92.9% / 85.7% |

![데모](docs/images/demo-answer.png)

## 실행

```bash
pip install -r requirements.txt
cp .env.example .env          # OPENAI_API_KEY 채우기
```

| 하고 싶은 것 | 명령 | API 호출 |
|---|---|---|
| 데모 화면 | `streamlit run app.py` | 문의마다 |
| 콘솔에서 물어보기 | `python chat.py "중개수수료 얼마예요?"` | 문의마다 |
| 전체 측정 | `python evaluate.py --tag 이름` | 약 170회 |
| 분류만 측정 | `python evaluate.py --only router` | 42회 |
| 저장된 답변 다시 채점 | `python evaluate.py --rescore runs/이름.json` | 채점만 |
| 채점기 자체 검증 | `python evaluate.py --validate` | 152회 |
| 실행 결과 문항별 비교 | `python scripts/compare_runs.py 이름1 이름2` | 없음 |
| 평가셋 형식·누출 검사 | `python scripts/check_goldenset.py` | 없음 |
| 검증기 오프라인 시험 | `python scripts/test_guardrail.py` | 없음 |
| 의미 수준 검증기 시험 (저장된 답변) | `python scripts/test_grounding.py` | 약 170회 |

## 파일 지도

| 파일 | 내용 |
|---|---|
| `docs/*.md` | 근거 문서 3종. 서비스 저장소에서 `scripts/export_docs.mjs`로 추출 |
| `docs/MAPPING.md` | 카테고리 설계와 조항 매핑 과정 |
| `data/goldenset_eval.json` | 평가용 42건. 별도 작성자가 문서만 보고 작성. **프롬프트에 넣지 않음** |
| `data/goldenset_fewshot.json` | 예시용 15건. 프롬프트에만 사용 |
| `data/judge_controls.json` | 채점기 검증용 오답 변형 95건 |
| `data/SCHEMA.md` | 평가셋 명세 |
| `context.py` | 조항 분할, 도구↔조항 표, 라우트별 도구 목록 |
| `prompts.py` | 분류 지침, 답변 규칙 |
| `router.py` | `classify`(LLM) · `gate`(확신도 정책) |
| `tools.py` · `answer.py` | 조항 조회 도구, 라우트별 도구 바인딩 호출 루프 |
| `guardrail.py` | 답변의 숫자·연락처·조항 인용이 조회한 조항에 있는지 검증 |
| `grounding.py` | 답변 문장마다 조회한 조항에 근거가 있는지 LLM 판정. 기본 꺼 둠(`RENTAL_GROUNDING_CHECK=1`로 켬, 실험 9) |
| `agent.py` | 전체 LangGraph 파이프라인 |
| `judge.py` · `evaluate.py` | 사실 단위 LLM 채점기, 측정 |
| `app.py` | Streamlit 데모 |
| `runs/LAB.md` | 실험 9회 기록과 실패 분석 |
| `runs/*.json` · `runs/*.log` | 측정별 문항 답변·채점 결과와 출력 |

## 지킨 것

- 평가용 문항은 프롬프트·데모 예시에 넣지 않음 (`prompts.py`가 import 시 검사)
- 한 번에 하나만 바꾸고 매번 2회 측정
- `.env`는 커밋하지 않음
