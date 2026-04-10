# ai_mini_project

## 핵심 기능 요약

- `Supervisor -> Company Discovery -> Web Search -> Report -> Formatting` 순서로 LangGraph 파이프라인을 실행합니다.
- 최신 반도체 웹 문서를 수집하고 날짜를 파싱한 뒤, 검색 결과를 JSON으로 저장하고 FAISS 인덱스로 구성합니다.
- retrieval 기반으로 한국어 기술 전략 보고서를 생성하고, Markdown과 PDF를 함께 출력합니다.
- 보고서에는 아래 3개 품질 지표를 함께 기록합니다.
- 최신도: 날짜 확인 가능 문서 비율, 최근 1년 문서 비율, 최신 문서 일자
- 정확도: 고신뢰 출처 비율
- 일관성: 동일 근거로 5회 반복 생성한 결론 일관성

## Workflow

`Supervisor -> Company Discovery -> Web Search -> Report -> Formatting`

- `Supervisor`: 단계 실행 순서와 재 시도 제어
- `Company Discovery`: 주요 경쟁사/협력사 탐색
- `Web Search`: 문서 수집, 날짜 파싱, JSON 저장, FAISS 인덱싱
- `Report`: retrieval 기반 보고서 작성, 결론 일관성 평가
- `Formatting`: 최종 Markdown 정리 및 PDF 렌더링

## Retrieval

- 검색 엔진: OpenAI Responses API `web_search_preview`
- 임베딩 모델: `sentence-transformers/all-MiniLM-L6-v2`
- 최종 선택: `Dense retrieval`
- 구현: `FAISS IndexFlatIP + recency bonus`

후보:

- 임베딩: `all-MiniLM-L6-v2`, `bge-small-en-v1.5`, `bge-base-en-v1.5`, `e5-base-v2`
- Retrieval 계열: `BM25`, `Dense`, `Hybrid(BM25 + Dense)`, `Dense + reranker`

선정 기준:

- 현재 문서 규모에서의 retrieval 품질
- 로컬 실행 속도와 메모리 사용량
- 구현 복잡도와 유지보수 단순성



metric:
웹검색 데이터를 저장하여 임의의 QA 셋을 만들어서 평가진행
`data/retrieval_eval_queries.json`

- Hit Rate@1: 0.50
- Hit Rate@3: 0.70
- Hit Rate@5: 0.90
- MRR: 0.62

## Run

전체 파이프라인:

```bash
python3 app.py \
  --technologies HBM4 PIM CXL \
  --output outputs/strategy_report.md
```

실행 결과:

- Markdown: `outputs/strategy_report.md`
- PDF: `outputs/strategy_report.pdf`
- 검색 데이터: `outputs/search_documents.json`
