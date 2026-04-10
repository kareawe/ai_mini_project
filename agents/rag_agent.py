"""
RAG Agent
- data/ 폴더의 PDF 문서를 청킹 & 임베딩하여 벡터 DB 구축
- HuggingFace 로컬 임베딩 (sentence-transformers)
- ChromaDB 영속 벡터 DB (재실행 시 재구축 생략)
- 기술별 쿼리로 관련 문서 검색 및 품질 스코어 계산
"""

import logging
from pathlib import Path
from typing import List, Optional

import fitz  # pymupdf
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from agents.states import RAGAgentState, Document

logger = logging.getLogger(__name__)

DATA_DIR   = Path("data")
CHROMA_DIR = Path("outputs/chroma_db")   # 영속 저장 경로
COLLECTION = "semiconductor_docs"
CHUNK_SIZE    = 800
CHUNK_OVERLAP = 100
TOP_K = 5

# 한국어+영어 모두 커버하는 다국어 모델
EMBED_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"

# ─────────────────────────────────────────────
# 임베딩 모델 (프로세스 내 싱글턴)
# ─────────────────────────────────────────────

_embed_model: Optional[SentenceTransformer] = None

def get_embed_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        logger.info(f"[RAG] 임베딩 모델 로드: {EMBED_MODEL_NAME}")
        _embed_model = SentenceTransformer(EMBED_MODEL_NAME)
    return _embed_model


def embed(texts: List[str]) -> List[List[float]]:
    """텍스트 리스트 → 벡터 리스트"""
    model = get_embed_model()
    return model.encode(texts, show_progress_bar=False).tolist()


# ─────────────────────────────────────────────
# PDF 로더 & 청커
# ─────────────────────────────────────────────

def load_pdf_documents(data_dir: Path = DATA_DIR) -> List[dict]:
    """data/ 폴더의 모든 PDF를 PyMuPDF로 파싱"""
    pdf_files = list(data_dir.glob("*.pdf")) if data_dir.exists() else []
    logger.info(f"[RAG] PDF {len(pdf_files)}개 발견: {[f.name for f in pdf_files]}")

    raw_docs = []
    for pdf_path in pdf_files:
        try:
            doc = fitz.open(str(pdf_path))
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
            raw_docs.append({"filename": pdf_path.name, "text": text})
            logger.info(f"[RAG] 파싱 완료: {pdf_path.name} ({len(text)}자)")
        except Exception as e:
            logger.error(f"[RAG] PDF 파싱 실패 {pdf_path.name}: {e}")

    return raw_docs


def chunk_documents(raw_docs: List[dict]) -> List[dict]:
    """텍스트를 CHUNK_SIZE 단위로 분할 (CHUNK_OVERLAP 중첩)"""
    chunks = []
    for doc in raw_docs:
        text = doc["text"]
        start = 0
        while start < len(text):
            end = start + CHUNK_SIZE
            chunk = text[start:end].strip()
            if chunk:
                chunks.append({
                    "filename": doc["filename"],
                    "chunk": chunk,
                    "chunk_id": f"{doc['filename']}_{start}",
                })
            start += CHUNK_SIZE - CHUNK_OVERLAP
    logger.info(f"[RAG] 총 청크 수: {len(chunks)}")
    return chunks


# ─────────────────────────────────────────────
# ChromaDB 벡터 DB
# ─────────────────────────────────────────────

def get_chroma_collection():
    """ChromaDB 컬렉션 반환 (없으면 생성)"""
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(
        name=COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )


def build_vector_store(chunks: List[dict]) -> None:
    """
    청크를 임베딩하여 ChromaDB에 저장.
    이미 저장된 chunk_id는 upsert로 중복 방지.
    """
    if not chunks:
        logger.warning("[RAG] 청크 없음 — 벡터 DB 구축 생략")
        return

    collection = get_chroma_collection()
    existing = set(collection.get()["ids"])

    new_chunks = [c for c in chunks if c["chunk_id"] not in existing]
    if not new_chunks:
        logger.info("[RAG] 모든 청크 이미 존재 — 재구축 생략")
        return

    logger.info(f"[RAG] 임베딩 중... ({len(new_chunks)}개 신규 청크)")
    texts     = [c["chunk"]    for c in new_chunks]
    ids       = [c["chunk_id"] for c in new_chunks]
    metadatas = [{"filename": c["filename"]} for c in new_chunks]
    vectors   = embed(texts)

    collection.upsert(
        ids=ids,
        embeddings=vectors,
        documents=texts,
        metadatas=metadatas,
    )
    logger.info(f"[RAG] ChromaDB 저장 완료: {len(new_chunks)}개")


def retrieve(query: str, top_k: int = TOP_K) -> List[Document]:
    """
    쿼리 임베딩 후 ChromaDB 코사인 유사도 검색.
    반환: 유사도 높은 순 Document 리스트
    """
    collection = get_chroma_collection()

    if collection.count() == 0:
        logger.warning("[RAG] 벡터 DB 비어 있음 — 검색 불가")
        return []

    query_vec = embed([query])[0]
    results = collection.query(
        query_embeddings=[query_vec],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    docs = []
    for content, meta, distance in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        # ChromaDB cosine distance → similarity (0~1)
        similarity = 1.0 - distance
        docs.append(Document(
            content=content,
            source=meta.get("filename", "unknown"),
            source_type="paper",
            technology=query.split()[0],
            relevance_score=round(similarity, 4),
        ))

    logger.info(f"[RAG] '{query}' → {len(docs)}개 검색 (최고 유사도: {docs[0].relevance_score if docs else 0})")
    return docs


def calculate_retrieval_quality(docs: List[Document]) -> float:
    """관련성 점수 평균"""
    if not docs:
        return 0.0
    return round(sum(d.relevance_score for d in docs) / len(docs), 4)


# ─────────────────────────────────────────────
# RAG Agent 메인 노드 함수
# ─────────────────────────────────────────────

def run_rag_agent(state: RAGAgentState) -> RAGAgentState:
    """RAG Agent 실행 엔트리포인트"""
    technologies = state.get("target_technologies", ["HBM4", "PIM", "CXL"])
    user_query   = state.get("user_query", "")

    logger.info(f"[RAG Agent] 시작 — 대상 기술: {technologies}")

    # 1. PDF 로드 → 청킹 → ChromaDB 구축
    raw_docs = load_pdf_documents()
    chunks   = chunk_documents(raw_docs)
    build_vector_store(chunks)

    # 2. 기술별 쿼리 검색
    all_docs: List[Document] = []
    for tech in technologies:
        query = f"{tech} {user_query}".strip()
        docs  = retrieve(query)
        all_docs.extend(docs)

    # 3. 품질 평가
    quality_score = calculate_retrieval_quality(all_docs)
    logger.info(f"[RAG Agent] 완료 — 문서 {len(all_docs)}개, 품질 점수: {quality_score}")

    state["retrieved_documents"]    = all_docs
    state["retrieval_quality_score"] = quality_score
    return state