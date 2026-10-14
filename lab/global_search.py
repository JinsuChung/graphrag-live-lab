"""커뮤니티 탐지 + 커뮤니티 리포트 + Map-Reduce (실습 05, 라이브 실험실 공용)."""
from __future__ import annotations

import json

import networkx as nx
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from common import DATA, triple_text


def detect_communities(G: nx.MultiDiGraph, seed: int = 42) -> list[list[str]]:
    """Louvain 커뮤니티 탐지 (MS GraphRAG 는 계층적 Leiden 사용)."""
    U = nx.Graph(G.to_undirected())
    return [sorted(c) for c in nx.community.louvain_communities(U, seed=seed)]


def community_text(G: nx.MultiDiGraph, members: list[str]) -> str:
    lines = [f"- {n}: {G.nodes[n]['description']}" for n in members]
    lines += [f"- {triple_text(u, v, d)}" for u, v, d in G.edges(data=True) if u in members and v in members]
    return "\n".join(lines)


class Report(BaseModel):
    title: str = Field(description="커뮤니티를 대표하는 짧은 제목")
    summary: str = Field(description="핵심 사실 3~4문장 요약")
    rating: int = Field(description="이 커뮤니티가 전체 도메인에서 갖는 중요도 0~10")


class Partial(BaseModel):
    answer: str = Field(description="이 요약만 근거로 한 부분 답변. 관련 없으면 빈 문자열")
    score: int = Field(description="질문과의 관련도 0~100")


REPORT_PROMPT = ChatPromptTemplate.from_template(
    "다음은 지식그래프의 한 커뮤니티(서로 밀접한 엔티티 묶음)입니다. 보고서를 작성하세요.\n\n{text}")
MAP_PROMPT = ChatPromptTemplate.from_template(
    "커뮤니티 보고서:\n{report}\n\n질문: {question}\n이 보고서만 근거로 부분 답변과 관련도를 주세요.")
REDUCE_PROMPT = ChatPromptTemplate.from_template(
    "다음은 여러 커뮤니티에서 모은 부분 답변입니다(점수 높은 순). 이를 종합해 질문에 답하세요.\n\n"
    "{partials}\n\n질문: {question}")


def precomputed_reports() -> list[dict]:
    return json.loads((DATA / "community_summaries.json").read_text(encoding="utf-8"))["communities"]


def similarity_scores(question: str, texts: list[str], embeddings) -> list[int]:
    """LLM 이 없을 때 Map 단계를 흉내 내는 대체 점수.

    질문과 각 리포트의 임베딩 코사인 유사도를 구해, 가장 높은 것을 100 으로 둔 상대 점수(0~100)로 바꾼다.
    """
    import math
    q = embeddings.embed_query(question)
    sims = []
    for v in embeddings.embed_documents(texts):
        dot = sum(a * b for a, b in zip(q, v))
        norm = math.sqrt(sum(a * a for a in q)) * math.sqrt(sum(b * b for b in v)) or 1.0
        sims.append(max(dot / norm, 0.0))
    top = max(sims) or 1.0
    return [round(100 * s / top) for s in sims]
