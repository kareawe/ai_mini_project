import json
import unicodedata
from pathlib import Path
from typing import List, Dict, Any

from agents.rag_agent import (
    load_pdf_documents,
    chunk_documents,
    build_vector_store,
    retrieve,
)

BASE_DIR = Path(__file__).resolve().parent
DATASET_PATH = BASE_DIR / "eval_dataset.json"
OUTPUT_PATH = BASE_DIR / "outputs" / "retrieval_eval_result.json"


def normalize_text(text: str) -> str:
    """
    한글 파일명 비교 시 유니코드 정규화 차이(NFC/NFD)로 인해
    문자열이 달라지는 문제를 방지.
    """
    if text is None:
        return ""
    return unicodedata.normalize("NFC", text).strip()


def hit_rate_at_k(results: List[Dict[str, Any]], k: int) -> float:
    if not results:
        return 0.0

    hit_count = 0
    for item in results:
        gold = normalize_text(item["gold_source"])
        top_k_sources = [normalize_text(s) for s in item["retrieved_sources"][:k]]

        if gold in top_k_sources:
            hit_count += 1

    return round(hit_count / len(results), 4)


def mrr(results: List[Dict[str, Any]]) -> float:
    if not results:
        return 0.0

    rr_sum = 0.0
    for item in results:
        gold_source = normalize_text(item["gold_source"])
        retrieved_sources = [normalize_text(s) for s in item["retrieved_sources"]]

        rank = 0
        for idx, source in enumerate(retrieved_sources, start=1):
            if source == gold_source:
                rank = idx
                break

        rr_sum += 0.0 if rank == 0 else 1.0 / rank

    return round(rr_sum / len(results), 4)


def evaluate_retrieval(top_k: int = 5) -> Dict[str, Any]:
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"평가 데이터셋이 없습니다: {DATASET_PATH}")

    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        eval_dataset = json.load(f)

    # 현재 RAG 파이프라인과 동일하게 문서 로드/청킹/벡터스토어 준비
    raw_docs = load_pdf_documents()
    chunks = chunk_documents(raw_docs)
    build_vector_store(chunks)

    per_question_results = []

    for row in eval_dataset:
        question = row["question"]
        gold_source = row["gold_source"]
        normalized_gold = normalize_text(gold_source)

        docs = retrieve(question, top_k=top_k)
        retrieved_sources = [doc.source for doc in docs]
        normalized_retrieved_sources = [normalize_text(s) for s in retrieved_sources]

        rank = 0
        for idx, source in enumerate(normalized_retrieved_sources, start=1):
            if source == normalized_gold:
                rank = idx
                break

        per_question_results.append(
            {
                "question": question,
                "gold_source": gold_source,
                "normalized_gold_source": normalized_gold,
                "retrieved_sources": retrieved_sources,
                "normalized_retrieved_sources": normalized_retrieved_sources,
                "rank": rank,
                "hit": rank > 0,
            }
        )

    metrics = {
        "num_questions": len(per_question_results),
        f"hit_rate@{top_k}": hit_rate_at_k(per_question_results, top_k),
        "mrr": mrr(per_question_results),
        "details": per_question_results,
    }

    return metrics


def main():
    OUTPUT_PATH.parent.mkdir(exist_ok=True)

    result = evaluate_retrieval(top_k=5)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("\n=== Retrieval Evaluation Result ===")
    print(f"질문 수        : {result['num_questions']}")
    print(f"Hit Rate@5    : {result['hit_rate@5']}")
    print(f"MRR           : {result['mrr']}")
    print(f"저장 경로      : {OUTPUT_PATH}")

    print("\n--- 상세 결과 ---")
    for item in result["details"]:
        print(f"Q: {item['question']}")
        print(f"Gold: {item['gold_source']}")
        print(f"Retrieved: {item['retrieved_sources']}")
        print(f"Rank: {item['rank']} | Hit: {item['hit']}")
        print("-" * 60)


if __name__ == "__main__":
    main()