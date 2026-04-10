# Subject

반도체 핵심 기술(HBM4, PIM, CXL) 경쟁력 분석 에이전트 시스템입니다.

공개된 PDF 및 웹 자료를 기반으로 반도체 핵심 기술의 기술 성숙도(TRL), 경쟁사 동향, 전략적 시사점을 도출하는 에이전트 기반 분석 시스템입니다. 코드베이스는 다중 에이전트(각 Agent는 독립 검증 및 출력)를 순차적으로 실행하여 최종 보고서를 생성합니다.

---

## Overview

- Objective: HBM4, PIM, CXL 관련 최신 동향과 기술 성숙도, 경쟁사(삼성전자, SK하이닉스, 마이크론 등) 관점의 위협/기회 분석 보고서 자동화
- Method: RAG 기반 문서 검색 → 웹 근거 보강 → 경쟁사 프로파일링 → Draft 생성 → 포맷팅
- Tools: Python, OpenAI API (chat/completions), 파일 기반 RAG 처리, Tavily 연동(웹 검색/임베딩)

---

## Features

## Features

- PDF 자료(PDF chunk) 기반 사실 추출 및 검증
- 웹 검색 기반 최신 동향 수집으로 최신성 보강
- 경쟁사 및 협력사 후보 추출 및 관계 유형 분류
- 검증된 사실 기반 Markdown 보고서 자동 생성 및 HTML/PDF 변환
- 출력은 `outputs/`에 raw, validated, drafts, final 등으로 분류 저장

---

## Tech Stack

## Tech Stack

| Category | Details                            |
| -------- | ---------------------------------- |
| Language | Python 3.10+                       |
| LLM      | OpenAI Chat API (설정된 모델 사용) |
| Web API  | Tavily (웹 검색/임베딩 키 필요)    |
| Storage  | 파일시스템 기반 (outputs/, data/)  |

| Vector DB | FAISS (로컬), Milvus / Weaviate (자체 또는 매니지드) - 임베딩 검색용으로 사용 가능; 기본 구현은 파일/FAISS 기반 RAG이나 환경에 따라 외부 벡터DB를 연결하여 확장하세요. |

---

## Agents

## Agents

- `RAG Agent` (`agents/rag_agent.py`): PDF 청크를 임베딩/검색하여 후보 사실(facts)을 추출하고 검증
- `Web Search Agent` (`agents/web_search_agent.py`): 웹 문서에서 사실 후보를 수집하고 보강
- `Competitor Listup Agent` (`agents/competitor_agent.py`): 기업 프로필 생성 및 관계 정리
- `Draft Generation Agent` (`agents/draft_agent.py`): 검증된 사실과 기업 프로필로 Markdown 보고서 초안 생성
- `Formatting Node` (`agents/formatting_node.py`): Markdown → HTML/PDF 변환 및 파일 저장

---

## Architecture

## Architecture

에이전트 기반 파이프라인(순차 실행):

RAG → Web Search → Competitor List-up → Draft Generation → Formatting

각 단계의 결과는 `outputs/` 아래에 JSON/markdown 형태로 저장되며, 상위 단계는 하위 단계의 `validated` 출력을 입력으로 사용합니다.

---

## Directory Structure

```
├── app.py                 # 실행 스크립트
├── agents/                # 에이전트 모듈
├── data/                  # PDF 및 입력 데이터
├── prompts/               # 프롬프트 템플릿
├── outputs/               # 에이전트 산출물 (raw, validated, drafts, final, logs)
├── requirement.txt        # 의존성
└── README.md
```

---

## Contributors

- 박하정 : Agent 설계, Prompt Engineering, 보고서 생성 로직 구현
- 윤민후 : 데이터 수집 및 전처리, Retrieval 및 분석 로직 구현
- 김민재 : Agent 실행 환경 구성 및 데이터 처리 지원
