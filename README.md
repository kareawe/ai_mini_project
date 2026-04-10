# ai_mini_project

LangGraph-based pipeline for:
- collecting recent HBM4, PIM, and CXL information
- identifying major companies relevant to each technology
- indexing collected evidence in FAISS
- generating a markdown technology strategy report for `SK hynix`

## Structure

- `app.py`: workflow entrypoint
- `agents/company_discovery.py`: company discovery node
- `agents/web_search.py`: web collection and FAISS indexing node
- `agents/report.py`: report generation node
- `prompts/company_discovery.py`: discovery prompt
- `prompts/web_search.py`: search prompt
- `prompts/report.py`: report prompt

## Requirements

- Python 3.9+
- `OPENAI_API_KEY` environment variable
- Installed packages: `faiss-cpu`, `sentence-transformers`

## Run

```bash
export OPENAI_API_KEY=your_key_here
python3 app.py \
  --technologies HBM4 PIM CXL \
  --output outputs/strategy_report.md
```

`.env` 파일에 `OPENAI_API_KEY=...` 형태로 넣어도 자동으로 읽습니다.

## Notes

- The workflow assumes `SK hynix` is the reference company.
- Company discovery excludes `SK hynix` from the discovered company list.
- FAISS 임베딩은 OpenAI가 아니라 `sentence-transformers/all-MiniLM-L6-v2`를 사용합니다.
- Search results are stored as structured documents with:
  - title
  - url
  - date
  - source_type
  - query_group
  - query_text
  - technology
  - company
  - content
- The final report is written as markdown under `outputs/`.
