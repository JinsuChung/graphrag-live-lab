"""실습 공통 유틸리티: 데이터 로딩, LLM/임베딩 초기화, 오프라인용 간이 임베딩."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path

import networkx as nx
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
load_dotenv(ROOT / ".env")


# ---------------------------------------------------------------------------
# 데이터 로딩
# ---------------------------------------------------------------------------
def load_docs() -> list[Document]:
    """data/docs/*.md 를 LangChain Document 리스트로 읽는다. doc_id = 'doc01' 형식."""
    docs = []
    paths = sorted((DATA / "docs").glob("*.md"))
    if not paths:
        raise SystemExit("data/docs 에 문서가 없습니다. 먼저 `python lab/00_prepare_pdf.py` 를 실행하세요 "
                         "(한국은행 보고서 PDF 를 받아 실습 문서를 만듭니다).")
    for path in paths:
        text = path.read_text(encoding="utf-8")
        title = text.splitlines()[0].lstrip("# ").strip()
        doc_id = path.stem.split("_")[0]
        docs.append(Document(page_content=text, metadata={"doc_id": doc_id, "title": title, "source": path.name}))
    return docs


def doc_by_id() -> dict[str, Document]:
    return {d.metadata["doc_id"]: d for d in load_docs()}


def load_kg(path: Path | None = None) -> nx.MultiDiGraph:
    """kg.json(노드/엣지 리스트)을 networkx 방향 멀티그래프로 변환한다.

    기본은 원문과 대조해 정리한 참조 그래프 data/kg.json (README 의 '참조 그래프' 참고). 실습 03 에서 LLM 으로 직접 추출했다면
    .env 에 KG_FILE=kg_extracted.json 을 넣어 그 그래프로 바꿔 실험할 수 있다.
    """
    raw = json.loads((path or DATA / os.getenv("KG_FILE", "kg.json")).read_text(encoding="utf-8"))
    G = nx.MultiDiGraph()
    for n in raw["nodes"]:
        G.add_node(n["id"], **{k: v for k, v in n.items() if k != "id"})
    for e in raw["edges"]:
        G.add_edge(e["source"], e["target"], key=e["type"], type=e["type"],
                   description=e.get("description", ""), doc=e.get("doc"))
    return G


def load_questions() -> list[dict]:
    return json.loads((DATA / "questions.json").read_text(encoding="utf-8"))


def evidence_recall(got: list[str], evidence: list[list[str]]) -> float:
    """근거 그룹 충족 비율. 그룹 = '이 문서들 중 하나만 찾으면 되는 사실 하나'.

    예) [["doc09"], ["doc11"]] → 두 사실이 필요, [["doc03", "doc01"]] → 둘 중 하나면 충족
    """
    return sum(any(d in got for d in group) for group in evidence) / len(evidence)


# ---------------------------------------------------------------------------
# LLM / 임베딩
# ---------------------------------------------------------------------------
def get_llm():
    """.env 의 LLM_MODEL(예: 'anthropic:claude-opus-5-5', 'openai:gpt-4.1-mini')로 채팅 모델 생성.

    LLM_MODEL 이 비어 있으면 None 을 돌려주고, 각 실습은 'LLM 없이 컨텍스트만 보는' 모드로 동작한다.
    """
    spec = os.getenv("LLM_MODEL", "").strip()
    if not spec:
        return None
    from langchain.chat_models import init_chat_model
    # 비스트리밍 호출이므로 출력 상한을 적당히 둔다 (너무 크면 SDK 가 스트리밍을 요구할 수 있음)
    kwargs = {"max_tokens": int(os.getenv("LLM_MAX_TOKENS", "16000"))}
    # LLM_TEMPERATURE: 교과서처럼 0 으로 두면 출력이 덜 흔들린다. 단, 최신 추론 모델 중에는
    # temperature 를 받지 않는 모델이 많다 (예: Claude 5 세대, GPT-6 Astra) → 그때는 비워 둔다.
    if os.getenv("LLM_TEMPERATURE", "").strip():
        kwargs["temperature"] = float(os.getenv("LLM_TEMPERATURE"))
    return init_chat_model(spec, **kwargs)


def get_embeddings() -> Embeddings:
    """.env 의 EMBEDDING_MODEL 로 임베딩 모델 생성.

    - 'local-ngram' 또는 빈 값: 인터넷/키 없이 도는 간이 임베딩 (수업 데모용)
    - 'huggingface:intfloat/multilingual-e5-small': 로컬 무료 한국어 지원 모델 (sentence-transformers 필요)
    - 'openai:text-embedding-3-small': OpenAI API
    """
    spec = os.getenv("EMBEDDING_MODEL", "").strip()
    if not spec or spec == "local-ngram":
        return CharNgramEmbeddings()
    from langchain.embeddings import init_embeddings
    return init_embeddings(spec)


class CharNgramEmbeddings(Embeddings):
    """문자 2~3-gram 을 해시해 만든 '가짜' 임베딩 (API 키 없이 실습하기 위한 대체재).

    의미를 이해하지 못하고 '글자가 얼마나 겹치는가'만 본다. 진짜 임베딩 모델의 동작을
    흉내 내기엔 충분하지만, 실제 서비스에서는 반드시 학습된 임베딩 모델을 써야 한다.
    """

    def __init__(self, dim: int = 2048):
        self.dim = dim

    def _embed(self, text: str) -> list[float]:
        text = re.sub(r"\s+", " ", text.lower())
        vec = [0.0] * self.dim
        for n in (2, 3):
            for i in range(len(text) - n + 1):
                gram = text[i:i + n]
                if gram.strip() == "":
                    continue
                h = int(hashlib.md5(gram.encode()).hexdigest(), 16)
                vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


# ---------------------------------------------------------------------------
# 출력 도우미
# ---------------------------------------------------------------------------
def header(title: str) -> None:
    print("\n" + "=" * 70 + f"\n{title}\n" + "=" * 70)


def triple_text(u: str, v: str, data: dict) -> str:
    desc = f" ({data['description']})" if data.get("description") else ""
    return f"{u} --[{data['type']}]--> {v}{desc}"
