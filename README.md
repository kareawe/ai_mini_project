# ai_mini_project

## Workflow

`Supervisor -> Company Discovery -> Web Search -> Report -> Formatting`

- `Supervisor`: 단계 실행 순서와 재시도 제어
- `Company Discovery`: 주요 경쟁사/협력사 탐색
- `Web Search`: 문서 수집, 날짜 파싱, JSON 저장, FAISS 인덱싱
- `Report`: retrieval 기반 보고서 작성, 결론 일관성 평가
- `Formatting`: 최종 Markdown 정리 및 PDF 렌더링

## Retrieval

- 검색 엔진: OpenAI Responses API `web_search_preview`
- 임베딩 모델: `sentence-transformers/all-MiniLM-L6-v2`
- Retrieval 방식: `Dense retrieval + FAISS + recency bonus`

후보:

- 임베딩: `all-MiniLM-L6-v2`, `bge-small-en-v1.5`, `bge-base-en-v1.5`, `e5-base-v2`
- Retrieval: `BM25`, `Dense`, `Hybrid(BM25 + Dense)`, `Dense + reranker`

선정 기준:

- 현재 문서 규모에서의 retrieval 품질
- 로컬 실행 속도와 메모리 사용량
- 구현 복잡도와 유지보수 단순성

평가 데이터:

- 로컬 `data/retrieval_eval_queries.json` 기준

metric:

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
