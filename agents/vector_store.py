from pathlib import Path
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from agents.utils import log_step


class VectorStore:
    def __init__(self, persist_dir: str, model_name: str):
        self.persist_dir = persist_dir

        self.client = chromadb.PersistentClient(path=persist_dir)

        self.embedding = SentenceTransformerEmbeddingFunction(
            model_name=model_name
        )

        self.collection = self.client.get_or_create_collection(
            name="rag_collection",
            embedding_function=self.embedding
        )

    def is_empty(self):
        return self.collection.count() == 0

    def add_documents(self, chunks):
        log_step("VectorDB", f"임베딩 저장 시작 (chunk {len(chunks)})")

        docs = [c["text"] for c in chunks]
        ids = [c["chunk_id"] for c in chunks]
        metadatas = [
            {
                "doc_name": c["doc_name"],
                "page": c["page"],
            }
            for c in chunks
        ]

        self.collection.add(
            documents=docs,
            ids=ids,
            metadatas=metadatas
        )

        log_step("VectorDB", "임베딩 저장 완료")

    def query(self, query, k):
        results = self.collection.query(
            query_texts=[query],
            n_results=k
        )

        docs = results["documents"][0]
        metas = results["metadatas"][0]

        output = []
        for doc, meta in zip(docs, metas):
            output.append({
                "text": doc,
                "doc_name": meta["doc_name"],
                "page": meta["page"],
                "chunk_id": f"{meta['doc_name']}_{meta['page']}"
            })

        return output