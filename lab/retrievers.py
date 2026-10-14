"""세 가지 검색기: 벡터 RAG / 그래프 RAG(로컬) / 하이브리드.

각 검색기는 두 가지 형태로 제공된다.
  - *_search_detailed(): 단계별 중간 결과를 모두 담은 dict (라이브 실험실 app/ 에서 시각화에 사용)
  - *_retrieve():        doc_id 리스트만 돌려주는 간단한 버전 (실습 스크립트에서 사용)
"""
from __future__ import annotations

from itertools import combinations

import networkx as nx
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter

from common import get_embeddings, load_docs, load_kg, triple_text

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

# ---------------------------------------------------------------------------
# 1) 벡터 RAG: 청크 → 임베딩 → 유사도 Top-k
# ---------------------------------------------------------------------------
_vector_store: InMemoryVectorStore | None = None


def make_splitter(chunk_size: int | None = None, overlap: int | None = None) -> RecursiveCharacterTextSplitter:
    """문단(\n\n) → 줄(\n) → 공백 → 글자 순으로 자를 곳을 찾는 LangChain 기본 분할기."""
    return RecursiveCharacterTextSplitter(chunk_size=chunk_size or CHUNK_SIZE,
                                          chunk_overlap=CHUNK_OVERLAP if overlap is None else overlap,
                                          add_start_index=True)


def build_vector_store() -> InMemoryVectorStore:
    """[인덱싱] 문서를 청크로 나누고 임베딩해 메모리 벡터 저장소에 넣는다 (한 번만 실행)."""
    global _vector_store
    if _vector_store is None:
        chunks = make_splitter().split_documents(load_docs())
        _vector_store = InMemoryVectorStore.from_documents(chunks, get_embeddings())
    return _vector_store


def vector_search_detailed(question: str, k: int = 3) -> dict:
    """[질의] 질문을 임베딩하고 모든 청크와의 코사인 유사도를 계산해 상위 문서를 고른다."""
    store = build_vector_store()
    query_vec = store.embedding.embed_query(question)
    # 모든 청크의 점수를 받아 온다 (시각화를 위해 k 대신 전체 개수)
    hits = store.similarity_search_with_score_by_vector(query_vec, k=len(store.store))
    scored = [{"doc_id": d.metadata["doc_id"], "text": d.page_content, "score": float(s)} for d, s in hits]
    doc_ids: list[str] = []
    context: list[dict] = []
    for h in scored:  # 점수 순으로 훑으며 서로 다른 문서 k개가 모일 때까지의 청크를 컨텍스트로 쓴다
        if len(doc_ids) == k:
            break
        context.append(h)
        if h["doc_id"] not in doc_ids:
            doc_ids.append(h["doc_id"])
    return {"query_vec": query_vec, "chunks": scored, "doc_ids": doc_ids, "context": context}


def vector_retrieve(question: str, k: int = 3) -> list[str]:
    return vector_search_detailed(question, k)["doc_ids"]


# ---------------------------------------------------------------------------
# 2) 그래프 RAG (Local Search)
#    ① 질문 속 엔티티 찾기(Entity Linking)
#    ② 시드 엔티티들을 잇는 최단 경로 (PathRAG 아이디어)
#    ③ 시드 주변 1-hop 서브그래프
#    ④ Personalized PageRank 로 노드 중요도 계산 (HippoRAG 아이디어)
#    ⑤ 경로 문서 우선 + PPR 점수로 원문 문서 순위화
# ---------------------------------------------------------------------------
_G: nx.MultiDiGraph | None = None


def get_graph() -> nx.MultiDiGraph:
    global _G
    if _G is None:
        _G = load_kg()
    return _G


def link_entities_detailed(question: str, G: nx.MultiDiGraph | None = None) -> list[dict]:
    """이름·별칭 문자열 매칭으로 질문에 등장하는 노드를 찾는다 (가장 단순한 Entity Linking).

    '혁신기업 신생률' 안의 '혁신기업'처럼 더 긴 매칭에 포함된 짧은 매칭은 버린다.
    """
    G = G or get_graph()
    found = []
    for node, data in G.nodes(data=True):
        best = None
        for name in [node, *data.get("aliases", [])]:
            pos = question.find(name)
            if pos >= 0 and (best is None or len(name) > best["end"] - best["start"]):
                best = {"node": node, "matched": name, "start": pos, "end": pos + len(name)}
        if best:
            found.append(best)
    return [f for f in found
            if not any(o is not f and o["start"] <= f["start"] and f["end"] <= o["end"]
                       and (o["end"] - o["start"]) > (f["end"] - f["start"]) for o in found)]


def link_entities(question: str, G: nx.MultiDiGraph | None = None) -> list[str]:
    return [f["node"] for f in link_entities_detailed(question, G)]


def shortest_paths(seeds: list[str], G: nx.MultiDiGraph, max_paths: int = 3) -> list[list[str]]:
    """시드 쌍마다 방향을 무시한 최단 경로(최대 max_paths 개)."""
    U = G.to_undirected(as_view=True)
    paths = []
    for a, b in combinations(seeds, 2):
        try:
            paths += list(nx.all_shortest_paths(U, a, b))[:max_paths]
        except nx.NetworkXNoPath:
            pass
    return paths


def edges_on_paths(paths: list[list[str]], G: nx.MultiDiGraph) -> list[tuple[str, str, dict]]:
    """경로를 이루는 실제 (방향 있는) 엣지를 경로 순서대로 반환."""
    edges = []
    for path in paths:
        for x, y in zip(path, path[1:]):
            for u, v in ((x, y), (y, x)):
                for data in (G.get_edge_data(u, v) or {}).values():
                    edges.append((u, v, data))
    return edges


def path_edges(seeds: list[str], G: nx.MultiDiGraph, max_paths: int = 3) -> list[tuple[str, str, dict]]:
    return edges_on_paths(shortest_paths(seeds, G, max_paths), G)


def expand_hops(seeds: list[str], G: nx.MultiDiGraph, hops: int = 1) -> dict[str, int]:
    """시드로부터 hops 이내 노드와 그 거리."""
    U = G.to_undirected(as_view=True)
    dist: dict[str, int] = {}
    for s in seeds:
        for n, d in nx.single_source_shortest_path_length(U, s, cutoff=hops).items():
            dist[n] = min(d, dist.get(n, d))
    return dist


def expand_subgraph(seeds: list[str], G: nx.MultiDiGraph, hops: int = 1) -> set[str]:
    nodes = set(expand_hops(seeds, G, hops))
    for p in shortest_paths(seeds, G):
        nodes |= set(p)
    return nodes


def personalized_pagerank(seeds: list[str], G: nx.MultiDiGraph) -> dict[str, float]:
    """시드에서 출발하는 Personalized PageRank.

    HippoRAG 처럼 시드마다 '특이도' 가중치를 준다: 여러 문서에 두루 나오는 일반적인 노드(예: R&D 지출)보다
    적은 문서에만 나오는 구체적인 노드(예: 은행 벤처캐피탈)를 더 중요한 출발점으로 본다.
    """
    U = nx.Graph(G.to_undirected())  # 멀티엣지를 단일 엣지로 합침
    spec = {n: 1.0 / max(1, len(G.nodes[n].get("docs", []))) for n in seeds}
    personalization = {n: spec.get(n, 0.0) for n in U}
    return nx.pagerank(U, alpha=0.85, personalization=personalization)


PATH_BONUS = 2.0  # 시드 사이 경로 위 관계의 가중치 (PathRAG 아이디어)


def graph_search_detailed(question: str, k: int = 3) -> dict:
    """그래프 로컬 검색의 모든 중간 결과를 반환."""
    G = get_graph()
    links = link_entities_detailed(question, G)
    seeds = [l["node"] for l in links]
    out = {"links": links, "seeds": seeds, "paths": [], "path_edges": [], "hops": {}, "sub": [],
           "ppr": {}, "doc_scores": [], "doc_ids": [], "triples": []}
    if not seeds:
        return out

    # ② 경로
    paths = shortest_paths(seeds, G)
    p_edges = edges_on_paths(paths, G)
    # ③ 1-hop 확장 (+경로 노드)
    hops = expand_hops(seeds, G, hops=1)
    sub = set(hops) | {n for p in paths for n in p}
    # ④ PPR
    ppr = personalized_pagerank(seeds, G)

    # ⑤ 문서 점수: 서브그래프 관계마다 (양 끝 노드의 PPR 합) × (경로 위면 PATH_BONUS) 를 출처 문서에 더한다
    on_path = {(u, v, d["type"]) for u, v, d in p_edges}
    doc_info: dict[str, dict] = {}
    scored_triples = []
    for u, v, data in G.edges(data=True):
        if u in sub and v in sub:
            path = (u, v, data["type"]) in on_path
            w = (ppr[u] + ppr[v]) * (PATH_BONUS if path else 1.0)
            info = doc_info.setdefault(data["doc"], {"doc_id": data["doc"], "via": "subgraph", "score": 0.0, "edges": []})
            info["score"] += w
            info["edges"].append(f"{u} -[{data['type']}]-> {v}")
            if path:
                info["via"] = "path"
            scored_triples.append((w, triple_text(u, v, data)))
    triples = [t for _, t in sorted(scored_triples, reverse=True)]
    doc_scores = sorted(doc_info.values(), key=lambda d: -d["score"])

    out.update({
        "paths": paths,
        "path_edges": [{"s": u, "t": v, "type": d["type"], "doc": d["doc"]} for u, v, d in p_edges],
        "hops": hops, "sub": sorted(sub), "ppr": ppr,
        "doc_scores": doc_scores, "doc_ids": [d["doc_id"] for d in doc_scores[:k]], "triples": triples[:15],
    })
    return out


def graph_retrieve(question: str, k: int = 3, return_context: bool = False):
    """그래프 로컬 검색. doc_id 리스트(와 선택적으로 시드·트리플 컨텍스트)를 반환."""
    r = graph_search_detailed(question, k)
    if return_context:
        return r["doc_ids"], r["seeds"], r["triples"]
    return r["doc_ids"]


# ---------------------------------------------------------------------------
# 3) 하이브리드: 그래프 결과와 벡터 결과를 번갈아 섞기
# ---------------------------------------------------------------------------
def interleave(a: list[str], b: list[str], k: int) -> list[str]:
    merged: list[str] = []
    for pair in zip(a + [None] * k, b + [None] * k):
        for d in pair:
            if d and d not in merged:
                merged.append(d)
    return merged[:k]


def hybrid_retrieve(question: str, k: int = 3) -> list[str]:
    return interleave(graph_retrieve(question, k=k), vector_retrieve(question, k=k), k)
