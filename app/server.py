"""GraphRAG 라이브 실험실 서버.

실행 (프로젝트 루트에서):
    python app/server.py            → http://localhost:8000

실습 코드(lab/)를 그대로 import 해서 실행하고, 각 단계의 중간 결과를 JSON 으로 돌려준다.
LLM 답변과 에이전트 탐색은 Server-Sent Events 로 실시간 스트리밍한다.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lab"))
sys.path.insert(0, str(ROOT / "app"))

import networkx as nx  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import pdf_prep  # noqa: E402

pdf_prep.ensure_docs()  # 처음 실행이면 보고서 PDF 를 받아 data/docs 를 만든다

import common  # noqa: E402
import pipelines  # noqa: E402
import retrievers as R  # noqa: E402
from global_search import detect_communities, precomputed_reports  # noqa: E402
from temporal_kg import Fact, demo_kg  # noqa: E402

app = FastAPI(title="GraphRAG Live Lab")


@app.middleware("http")
async def no_cache_static(request, call_next):
    """화면 파일을 고치면 새로고침만으로 바로 반영되도록 캐시를 끈다."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    return response
STATIC = ROOT / "app" / "static"

LLM = common.get_llm()
TEMPORAL = demo_kg()


# ---------------------------------------------------------------------------
# 설정 / 그래프
# ---------------------------------------------------------------------------
def available_embeddings() -> list[dict]:
    opts = [{"id": "local-ngram", "label": "간이 n-gram (키 불필요)"}]
    if importlib.util.find_spec("langchain_huggingface") and importlib.util.find_spec("sentence_transformers"):
        opts.append({"id": "huggingface:intfloat/multilingual-e5-small", "label": "multilingual-e5-small (로컬)"})
    if os.getenv("OPENAI_API_KEY"):
        opts.append({"id": "openai:text-embedding-3-small", "label": "OpenAI text-embedding-3-small"})
    return opts


def kg_layout(G: nx.MultiDiGraph) -> dict:
    """노드 좌표. data/kg_layout.json 이 현재 그래프와 맞으면 그대로 쓰고, 아니면 새로 계산."""
    cache = common.DATA / "kg_layout.json"
    if cache.exists():
        pos = json.loads(cache.read_text(encoding="utf-8"))
        if set(pos) == set(G.nodes):
            return pos
    U = nx.Graph(G.to_undirected())
    try:
        raw = nx.kamada_kawai_layout(U)  # scipy 필요
    except ImportError:
        raw = nx.spring_layout(U, seed=7, k=0.9)
    xs, ys = [p[0] for p in raw.values()], [p[1] for p in raw.values()]
    W, H, pad = 960, 620, 60
    pos = {n: [round(pad + (p[0] - min(xs)) / (max(xs) - min(xs)) * (W - 2 * pad), 1),
               round(pad + (p[1] - min(ys)) / (max(ys) - min(ys)) * (H - 2 * pad), 1)] for n, p in raw.items()}
    if os.getenv("KG_FILE", "kg.json") == "kg.json":
        cache.write_text(json.dumps(pos, ensure_ascii=False), encoding="utf-8")
    return pos


@app.get("/api/config")
def config():
    G = R.get_graph()
    pos = kg_layout(G)
    comms = detect_communities(G)
    comm_of = {n: i for i, c in enumerate(comms) for n in c}
    return {
        "llm": os.getenv("LLM_MODEL") if LLM else None,
        "embedding": os.getenv("EMBEDDING_MODEL") or "local-ngram",
        "embeddings": available_embeddings(),
        "kg_file": os.getenv("KG_FILE", "kg.json"),
        "chunking": {"chunk_size": R.CHUNK_SIZE, "overlap": R.CHUNK_OVERLAP},
        "questions": common.load_questions(),
        "docs": [{"id": d.metadata["doc_id"], "title": d.metadata["title"], "file": "data/docs/" + d.metadata["source"]}
                 for d in common.load_docs()],
        "kg": {
            "nodes": [{"id": n, "type": d["type"], "description": d["description"], "docs": d.get("docs", []),
                       "x": pos[n][0], "y": pos[n][1], "c": comm_of[n]} for n, d in G.nodes(data=True)],
            "edges": [{"s": u, "t": v, "type": d["type"], "desc": d.get("description", ""), "doc": d.get("doc")}
                      for u, v, d in G.edges(data=True)],
        },
        "communities": precomputed_reports(),
    }


class EmbeddingReq(BaseModel):
    embedding: str


@app.post("/api/config/embedding")
def set_embedding(req: EmbeddingReq):
    if req.embedding not in {o["id"] for o in available_embeddings()}:
        raise HTTPException(400, "사용할 수 없는 임베딩입니다")
    os.environ["EMBEDDING_MODEL"] = req.embedding
    R._vector_store = None  # 다음 검색 때 새 임베딩으로 다시 인덱싱
    t0 = time.perf_counter()
    R.build_vector_store()
    return {"embedding": req.embedding, "index_ms": round((time.perf_counter() - t0) * 1000)}


# ---------------------------------------------------------------------------
# 파이프라인 추적
# ---------------------------------------------------------------------------
class TraceReq(BaseModel):
    mode: str
    question: str
    k: int = 5


@app.post("/api/trace")
def trace(req: TraceReq):
    q = req.question.strip()
    if not q:
        raise HTTPException(400, "질문을 입력하세요")
    if req.mode == "vector":
        return pipelines.vector_trace(q, req.k)
    if req.mode == "graph":
        return pipelines.graph_trace(q, req.k)
    if req.mode == "global":
        return pipelines.global_trace(q, LLM)
    raise HTTPException(400, f"알 수 없는 모드: {req.mode}")


@app.post("/api/compare")
def compare(req: TraceReq):
    return pipelines.compare(req.question.strip(), req.k)


@app.get("/api/benchmark")
def benchmark(k: int = 5):
    return pipelines.benchmark(k)


class IngestReq(BaseModel):
    page: int = 3
    doc_id: str = "doc09"
    chunk_size: int = 500
    overlap: int = 50


@app.post("/api/ingest")
def ingest(req: IngestReq):
    return pipelines.ingest_trace(req.page, req.doc_id, req.chunk_size, req.overlap)


@app.post("/api/ingest/chunks")
def ingest_chunks(req: IngestReq):
    if not (50 <= req.chunk_size <= 4000) or not (0 <= req.overlap < req.chunk_size):
        raise HTTPException(400, "청크 크기는 50~4000, 겹침은 0 이상 청크 크기 미만이어야 합니다")
    return pipelines.chunk_view(req.doc_id, req.chunk_size, req.overlap)


@app.post("/api/config/chunking")
def set_chunking(req: IngestReq):
    """벡터 인덱스를 새 청크 설정으로 다시 만든다 (이후 벡터 RAG 모드에 반영)."""
    if not (50 <= req.chunk_size <= 4000) or not (0 <= req.overlap < req.chunk_size):
        raise HTTPException(400, "청크 크기는 50~4000, 겹침은 0 이상 청크 크기 미만이어야 합니다")
    R.CHUNK_SIZE, R.CHUNK_OVERLAP = req.chunk_size, req.overlap
    R._vector_store = None
    t0 = time.perf_counter()
    store = R.build_vector_store()
    return {"chunk_size": R.CHUNK_SIZE, "overlap": R.CHUNK_OVERLAP, "chunks": len(store.store),
            "index_ms": round((time.perf_counter() - t0) * 1000)}


class ExtractReq(BaseModel):
    doc_id: str | None = "doc14"
    text: str | None = None


@app.post("/api/extract")
def extract(req: ExtractReq):
    return pipelines.extract_trace(req.doc_id, req.text, LLM)


# ---------------------------------------------------------------------------
# 스트리밍: LLM 답변, 에이전트
# ---------------------------------------------------------------------------
def sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


class AnswerReq(BaseModel):
    messages: list[dict]


@app.post("/api/answer")
async def answer(req: AnswerReq):
    async def gen():
        if LLM is None:
            yield sse({"error": "LLM_MODEL 이 설정되지 않았습니다. .env 에 LLM_MODEL 과 API 키를 넣고 서버를 다시 시작하세요. "
                                "(검색 단계까지는 LLM 없이도 모두 실행됩니다)"})
            return
        t0, first, agg = time.perf_counter(), None, None
        try:
            async for chunk in LLM.astream(req.messages):
                agg = chunk if agg is None else agg + chunk
                if chunk.text:
                    first = first or time.perf_counter()
                    yield sse({"t": chunk.text})
        except Exception as e:  # 키 오류, 네트워크 오류 등을 화면에 그대로 보여 준다
            yield sse({"error": f"{type(e).__name__}: {e}"})
            return
        usage = getattr(agg, "usage_metadata", None) or {}
        yield sse({"done": True, "ttft_ms": round(((first or time.perf_counter()) - t0) * 1000),
                   "total_ms": round((time.perf_counter() - t0) * 1000),
                   "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens")})
    return StreamingResponse(gen(), media_type="text/event-stream")


class AgentReq(BaseModel):
    question: str


@app.post("/api/agent")
async def agent(req: AgentReq):
    async def gen():
        if LLM is None:
            yield sse({"error": "에이전트는 LLM 이 필요합니다. .env 에 LLM_MODEL 과 API 키를 설정하세요."})
            return
        from langchain.agents import create_agent
        from langchain_core.messages import AIMessage, ToolMessage

        from graph_tools import SYSTEM, TOOLS
        ag = create_agent(LLM, tools=TOOLS, system_prompt=SYSTEM)
        t0 = time.perf_counter()
        try:
            async for update in ag.astream({"messages": [{"role": "user", "content": req.question}]},
                                           stream_mode="updates"):
                for payload in update.values():
                    if not isinstance(payload, dict):
                        continue
                    for m in payload.get("messages", []):
                        ms = round((time.perf_counter() - t0) * 1000)
                        if isinstance(m, AIMessage):
                            if m.text:
                                yield sse({"type": "thought" if m.tool_calls else "final", "text": m.text, "ms": ms})
                            for tc in m.tool_calls:
                                yield sse({"type": "tool_call", "name": tc["name"], "args": tc["args"], "ms": ms})
                        elif isinstance(m, ToolMessage):
                            yield sse({"type": "tool_result", "name": m.name, "content": str(m.content)[:2000], "ms": ms})
        except Exception as e:
            yield sse({"type": "error", "text": f"{type(e).__name__}: {e}"})
        yield sse({"type": "done", "ms": round((time.perf_counter() - t0) * 1000)})
    return StreamingResponse(gen(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# 시간 인식 메모리
# ---------------------------------------------------------------------------
class FactReq(BaseModel):
    source: str
    relation: str
    target: str
    valid_from: str
    episode: str = ""


@app.get("/api/temporal")
def temporal_state():
    return {"facts": TEMPORAL.as_dicts(), "exclusive": sorted(TEMPORAL.exclusive)}


@app.post("/api/temporal/add")
def temporal_add(req: FactReq):
    inv = TEMPORAL.add(Fact(**req.model_dump()))
    return {"invalidated": [f"{f.source} -[{f.relation}]-> {f.target}" for f in inv], **temporal_state()}


@app.post("/api/temporal/reset")
def temporal_reset():
    global TEMPORAL
    TEMPORAL = demo_kg()
    return temporal_state()


@app.get("/api/temporal/query")
def temporal_query(source: str, relation: str, as_of: str):
    return {"answer": TEMPORAL.query(source, relation, as_of)}


# ---------------------------------------------------------------------------
# 코드·데이터 뷰어
# ---------------------------------------------------------------------------
def project_files() -> list[str]:
    files = ["README.md", "requirements.txt", ".env.example", "docker-compose.yml"]
    files += sorted(str(p.relative_to(ROOT)) for p in (ROOT / "lab").glob("*.py"))
    files += sorted(str(p.relative_to(ROOT)) for p in (ROOT / "data").rglob("*") if p.is_file())
    files += sorted(str(p.relative_to(ROOT)) for p in (ROOT / "app").rglob("*")
                    if p.is_file() and "__pycache__" not in p.parts)
    text_ext = {".py", ".md", ".json", ".txt", ".yml", ".example", ".html", ".css", ".js"}
    return [f for f in files if (ROOT / f).exists() and Path(f).suffix in text_ext]


@app.get("/api/pdf")
def pdf():
    """원본 보고서 PDF (브라우저 새 탭에서 열기용)."""
    from pdf_prep import PDF_PATH
    return FileResponse(PDF_PATH, media_type="application/pdf")


@app.get("/api/files")
def files():
    return project_files()


@app.get("/api/file")
def file(path: str):
    if path not in project_files():
        raise HTTPException(404, "파일이 없습니다")
    return {"path": path, "content": (ROOT / path).read_text(encoding="utf-8")}


@app.get("/api/coderef")
def coderef(file: str, symbol: str):
    """함수/클래스/변수 이름으로 소스 코드의 줄 범위를 찾는다 ('코드 보기' 버튼용)."""
    if file not in project_files() or not file.endswith(".py"):
        raise HTTPException(404, "파일이 없습니다")
    tree = ast.parse((ROOT / file).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        names = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if symbol in names:
            return {"file": file, "start": node.lineno, "end": node.end_lineno}
    return {"file": file, "start": 1, "end": 1}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "127.0.0.1")  # 학생 노트북에서 접속하게 하려면 HOST=0.0.0.0 (같은 네트워크)
    print(f"\n  GraphRAG 라이브 실험실 → http://localhost:{port}")
    print(f"  LLM: {os.getenv('LLM_MODEL') if LLM else '없음 (검색 단계만 실행)'}"
          f" · 임베딩: {os.getenv('EMBEDDING_MODEL') or 'local-ngram'}\n")
    uvicorn.run(app, host=host, port=port)
