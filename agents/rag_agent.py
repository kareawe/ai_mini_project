from __future__ import annotations

from pathlib import Path
from typing import List

from pypdf import PdfReader

from agents.config import AppConfig
from agents.llm_client import LLMClient
from agents.models import AgentRunResult, EvidenceItem, RunContext, ValidatedFact
from agents.utils import dump_json, normalize_whitespace, simple_chunk_text, log_step
from agents.vector_store import VectorStore
from prompts.system_prompts import RAG_EXTRACTION_SYSTEM_PROMPT


class RAGAgent:
    def __init__(self, config: AppConfig, context: RunContext) -> None:
        self.config = config
        self.context = context
        self.llm = LLMClient(config)

        # 벡터 DB 연결 
        self.vector_store = VectorStore(
            persist_dir=str(Path(self.context.outputs_dir) / "vector_db"),
            model_name=self.config.embedding_model_name
        )

    def _load_pdf_chunks(self) -> List[dict]:
        data_dir = Path(self.context.data_dir)
        pdf_paths = sorted(data_dir.glob("*.pdf"))
        chunks: List[dict] = []

        log_step("RAGAgent", f"PDF 파일 {len(pdf_paths)}개 발견")

        for pdf_path in pdf_paths:
            log_step("RAGAgent", f"PDF 로딩 시작: {pdf_path.name}")
            reader = PdfReader(str(pdf_path))

            doc_chunk_count = 0

            for page_idx, page in enumerate(reader.pages, start=1):
                text = normalize_whitespace(page.extract_text() or "")
                if not text:
                    continue

                page_chunks = simple_chunk_text(
                    text,
                    self.config.chunk_size,
                    self.config.chunk_overlap,
                )

                for chunk_idx, chunk in enumerate(page_chunks, start=1):
                    chunks.append(
                        {
                            "doc_name": pdf_path.name,
                            "page": page_idx,
                            "chunk_id": f"{pdf_path.stem}_p{page_idx}_c{chunk_idx}",
                            "text": chunk,
                        }
                    )

                doc_chunk_count += len(page_chunks)

            log_step("RAGAgent", f"PDF 처리 완료: {pdf_path.name} / chunk 수 {doc_chunk_count}")

        log_step("RAGAgent", f"전체 chunk 수: {len(chunks)}")
        return chunks

    def _build_query(self, attempt: int) -> str:
        base = (
            "HBM4 PIM CXL semiconductor technology review architecture limitation "
            "thermal memory pooling near-memory processing TRL"
        )
        if attempt == 0:
            return base
        return base + " survey overview constraints industrial relevance"

    def _validate(self, facts: List[ValidatedFact]) -> tuple[bool, list[str]]:
        warnings: List[str] = []

        technologies = {fact.technology.upper() for fact in facts}

        if len(facts) < 5:
            warnings.append("RAG 근거 fact 수가 부족합니다.")

        if not {"PIM", "CXL"}.issubset(technologies):
            warnings.append("PIM/CXL 커버리지가 부족합니다.")

        return len(warnings) == 0, warnings

    def run(self) -> AgentRunResult:
        log_step("RAGAgent", "RAG Agent 시작")

        data_dir = Path(self.context.data_dir)
        pdf_paths = sorted(data_dir.glob("*.pdf"))

        if not pdf_paths:
            log_step("RAGAgent", "실패: data 폴더에 PDF 없음")
            return AgentRunResult(
                agent_name="RAGAgent",
                status="failed",
                retry_count=0,
                validation_passed=False,
                warnings=["PDF 없음"],
            )

        vector_path = Path(self.context.outputs_dir) / "vector_db"

        if not vector_path.exists():
            log_step("RAGAgent", "Vector DB 없음 → 최초 1회 임베딩 수행")

            chunks = self._load_pdf_chunks()
            self.vector_store.add_documents(chunks)

        else:
            log_step("RAGAgent", "기존 Vector DB 재사용 (임베딩 생략)")

        raw_items: List[EvidenceItem] = []
        validated_facts: List[ValidatedFact] = []
        warnings: List[str] = []

        for attempt in range(self.config.max_retry_rag + 1):
            log_step("RAGAgent", f"시도 {attempt + 1}/{self.config.max_retry_rag + 1}")

            query = self._build_query(attempt)
            log_step("RAGAgent", "검색 query 생성 완료")

            # 🔍 벡터 검색
            top_chunks = self.vector_store.query(query, self.config.rag_top_k)

            log_step("RAGAgent", f"검색 결과 chunk 수: {len(top_chunks)}")

            raw_items = [
                EvidenceItem(
                    title=f"{c['doc_name']} | p.{c['page']}",
                    source_type="rag_pdf",
                    snippet=c["text"][:500],
                    content=c["text"],
                    relevance_score=0.9,
                    confidence_score=0.9,
                    metadata={
                        "doc_name": c["doc_name"],
                        "page": c["page"],
                        "chunk_id": c["chunk_id"],
                    },
                )
                for c in top_chunks
            ]

            prompt_input = {
                "user_query": self.context.user_query,
                "target_technologies": self.context.target_technologies,
                "retrieved_chunks": [
                    {
                        "evidence_id": item.metadata["chunk_id"],
                        "title": item.title,
                        "content": item.content,
                    }
                    for item in raw_items
                ],
            }

            log_step("RAGAgent", "LLM fact 추출 요청 시작")

            result_json = self.llm.chat_json(
                system_prompt=RAG_EXTRACTION_SYSTEM_PROMPT,
                user_prompt=str(prompt_input),
            )

            log_step("RAGAgent", "LLM fact 추출 완료")

            validated_facts = []

            for fact in result_json.get("facts", []):
                validated_facts.append(
                    ValidatedFact(
                        claim=fact.get("claim", ""),
                        technology=fact.get("technology", "UNKNOWN"),
                        company=fact.get("company"),
                        trl_signal=fact.get("trl_signal"),
                        threat_signal=fact.get("threat_signal"),
                        confidence=float(fact.get("confidence", 0.5)),
                        evidence_ids=fact.get("evidence_ids", []),
                        evidence_summary=fact.get("evidence_summary", ""),
                        source_types=fact.get("source_types", ["rag_pdf"]),
                        caveat=fact.get("caveat", ""),
                    )
                )

            log_step("RAGAgent", f"검증 대상 fact 수: {len(validated_facts)}")

            passed, warnings = self._validate(validated_facts)

            if passed:
                log_step("RAGAgent", "검증 통과")

                output = AgentRunResult(
                    agent_name="RAGAgent",
                    status="success",
                    retry_count=attempt,
                    validation_passed=True,
                    warnings=[],
                    raw_items=raw_items,
                    validated_facts=validated_facts,
                    extra={"query": query},
                )

                dump_json(
                    Path(self.context.outputs_dir) / "validated" / f"rag_result_{self.context.run_id}.json",
                    output.model_dump(),
                )

                return output

            log_step("RAGAgent", f"검증 실패: {warnings}")

        status = "partial" if validated_facts else "failed"

        return AgentRunResult(
            agent_name="RAGAgent",
            status=status,
            retry_count=self.config.max_retry_rag,
            validation_passed=False,
            warnings=warnings,
            raw_items=raw_items,
            validated_facts=validated_facts,
        )