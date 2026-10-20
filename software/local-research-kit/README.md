# local-research-kit

Search a directory of Markdown notes, optionally ask a local model to summarize the matches, and keep the source lines beside the answer.

The default mode returns excerpts directly. No model, embedding service or external API is required.

```bash
python -m pip install -r requirements.txt
python -m localresearch index --notes notes
python -m localresearch ask "共同随机数有什么作用"
python -m uvicorn localresearch.api:app --host 127.0.0.1 --port 8001
```

Open <http://127.0.0.1:8001> for the browser interface. Uploads are UTF-8 `.md` or `.txt` files. The bundled notes are short examples written for this project.

## Retrieval

`index.py` splits documents at headings and line boundaries. Each chunk carries its relative path, source lines and a content-derived ID. SQLite FTS5 ranks English terms and Chinese bigrams with BM25. This is lexical retrieval, not a vector embedding index.

Index updates run in a transaction. Unchanged file hashes are skipped; changed and deleted files have their old chunks removed. Files reached through an external symlink are skipped. The local database lives in `.local/` and is not committed.

A small lexical-coverage filter suppresses some weak matches. Its score is not calibrated confidence, and unrelated questions sharing vocabulary can still return matches.

`pipeline.py` selects complete chunks within a configurable character budget, removes duplicate IDs and limits each document's share of the context. This is a text-size budget, not exact model-token accounting. Oversized chunks are skipped rather than silently changing their source lines.

## Run records

```bash
python -m localresearch ask "共同随机数有什么作用" --record .local/run.json
python -m localresearch replay .local/run.json
```

Records contain the selected source text, configuration, prompt version, input hash and stage timings. Replay uses the saved context, independently of the current index. It defaults to excerpt mode; pass an explicit backend to regenerate with a model. The hash detects accidental input edits, not authenticated tampering. Changing a model or its version may change generated output.

Saving a record also saves its question and source excerpts. Keep private records out of a public repository. The API returns trace data but does not automatically persist it. A small example is in `docs/trace-demo.json`.

## Local generation

Two optional backends use the same source-checking pipeline.

**Ollama**

Start a local Ollama service and use an already available model

```bash
python -m localresearch ask "为什么按受访者划分测试集" --backend ollama --model YOUR_LOCAL_MODEL
```

The endpoint defaults to `http://127.0.0.1:11434`. `LOCAL_RESEARCH_OLLAMA_URL` can change its port, but the adapter only accepts loopback HTTP hosts.

**GGUF / llama.cpp**

Install `llama-cpp-python` using the [upstream instructions](https://github.com/abetlen/llama-cpp-python), including the appropriate CPU or GPU build for your machine. `requirements-gguf.txt` records the version used for the integration.

```powershell
$env:LOCAL_RESEARCH_GGUF = "D:\models\model.gguf"
python -m localresearch ask "共同随机数有什么作用" --backend gguf
python -m localresearch.benchmark --backend gguf --model local-gguf
```

Weights are downloaded separately from their publisher and retain their own license. They are neither bundled nor presented as a model trained by this project. The GGUF adapter currently uses CPU defaults with a 4096-token context; a large retrieved context may exceed that budget and fall back to excerpts.

## Answer checks

The model is asked for structured items containing a statement, source ID and exact quote. Unknown IDs, missing fields and quotes not present in the selected source are filtered out. Text from the documents receives no tools or execution privileges.

Generation uses short source aliases and a schema restricting the allowed IDs. Aliases are mapped back to content-derived chunk IDs after generation. The raw text still needs independent quote validation.

These checks verify the citation mechanics. They do **not** prove that a generated statement logically follows from its quote, nor do they make arbitrary documents safe or correct. Check the cited text before relying on an answer. No matching excerpts produces an empty result; model errors produce an explicit excerpt fallback. Empty generated items remain empty instead of being quietly presented as a successful model answer.

## Evaluation

```bash
python -m localresearch evaluate
python -m pytest -q
```

[`evaluation.jsonl`](evaluation.jsonl) contains eight relevant queries and two unrelated queries. The committed retrieval record reports document hit rate and reciprocal rank over this small hand-written set. It is a smoke check tied to these notes, not an independent benchmark or a general accuracy claim.

`localresearch.benchmark` saves a few actual backend responses, wall-clock times and citation-filter decisions. The first call includes model loading. Citation validity is reported separately from whether the model returned an answer. There is no automatic factuality score.

An actual CPU run with Qwen3-0.6B-Q8_0 is recorded in [`docs/generation-notes.md`](docs/generation-notes.md), including an initial rejected answer and the schema-constrained rerun. Model metadata and the weight checksum are recorded separately from the application code.

## Layout

```text
localresearch/index.py        SQLite ingestion and search
localresearch/generation.py   model adapters and quote validation
localresearch/pipeline.py     bounded context selection and replay
localresearch/evaluation.py   retrieval smoke checks
localresearch/benchmark.py    local generation records
localresearch/api.py          local HTTP interface
web/                         plain browser client
notes/                       example corpus
tests/                       input, indexing and evidence checks
```

The server is intended for one local user. It has no accounts, public deployment configuration or persistent chat history. Bind it to `127.0.0.1`; document text and questions are passed only to the configured local backend. The browser displays model content as text, not HTML.

API details follow the [Ollama chat documentation](https://docs.ollama.com/api/chat). The GGUF smoke model is described in the [Qwen model card](https://huggingface.co/Qwen/Qwen3-0.6B-GGUF).
