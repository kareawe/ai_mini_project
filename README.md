# ai_mini_project

## Overview
반도체 핵심 기술(HBM4, PIM, CXL)에 대해 경쟁사 기술 수준과 전략을 분석하고,  
이를 자동으로 보고서(PDF) 형태로 생성하는 AI Agent 기반 시스템이다.

데이터 수집부터 보고서 생성까지 전 과정을 자동화한 End-to-End 분석 모델이다.

---
## Architecture

```text
User Query
   ↓
Supervisor
   ├── RAG Agent (문서 기반 정보 수집)
   ├── Web Search Agent (최신 정보 수집)
   ├── Competitor Agent (경쟁사 식별)
   ↓
Draft Agent (보고서 생성)
   ↓
Formatting Node (PDF 변환)
   ↓
Final Report
```
## Core Components

### Supervisor
- 전체 워크플로우 제어
- Agent 간 작업 분배 및 결과 통합

### RAG Agent
- 기술 문서 기반 검색
- 컨텍스트 생성

### Web Search Agent
- 최신 기술 동향 및 뉴스 수집

### Competitor Agent
- 경쟁사 리스트업 및 분석 대상 정의

### Draft Agent
- 구조화된 보고서 생성
- 기술 비교 및 전략 도출

### Formatting Node
- Markdown → PDF 변환
- 표, 제목, 리스트 등 스타일링 적용

---

## Report Structure

- SUMMARY
- 1. 분석 배경 및 방법론
- 2. 분석 대상 기술 현황
- 3. 경쟁사 동향 분석
- 4. 전략적 시사점
- REFERENCE

---

## Pipeline

1. 사용자 질의 입력  
2. 데이터 수집 (RAG + Web)  
3. 경쟁사 분석  
4. 보고서 초안 생성  
5. PDF 변환  
6. 최종 결과 출력  

---

## Features

- End-to-End 분석 자동화
- Agent 기반 모듈 구조
- 전략 보고서 형태 출력
- 확장 가능한 구조 설계

---

## Run

```bash
python main.py \
  --query "HBM4, PIM, CXL 기술 경쟁사 전략 분석" \
  --techs HBM4 PIM CXL

  
