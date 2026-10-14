"""에이전트용 그래프 탐색 도구 (실습 08, 라이브 실험실 공용)."""
import networkx as nx
from langchain_core.tools import tool

from common import doc_by_id, get_lang, t, triple_text
from retrievers import get_graph



def _g():
    return get_graph()


def _docs():
    return doc_by_id()


@tool
def search_entities(keyword: str) -> str:
    """Find graph entities whose name, alias or description contains the keyword. Use it to pick a starting point. (키워드로 엔티티 찾기)"""
    k = keyword.lower()
    hits = [
        f"{n} ({d['type']}): {d['description']}"
        for n, d in _g().nodes(data=True)
        if k in n.lower() or any(k in a.lower() for a in d.get("aliases", [])) or k in d["description"].lower()
    ]
    return "\n".join(hits) or "결과 없음"


@tool
def get_neighbors(entity: str) -> str:
    """List all relations (in/out edges) of an entity as triples, with source document ids. (엔티티의 관계 보기)"""
    G = _g()
    if entity not in G:
        return t(f"'{entity}' 노드가 없습니다. search_entities 로 정확한 이름을 먼저 찾으세요.",
                 f"No node named '{entity}'. Use search_entities to find the exact name first.")
    edges = list(G.out_edges(entity, data=True)) + list(G.in_edges(entity, data=True))
    return "\n".join(f"{triple_text(u, v, d)} [출처 {d['doc']}]" for u, v, d in edges)


@tool
def find_path(source: str, target: str) -> str:
    """Find the shortest connecting path between two entities, for causal or indirect links. (두 엔티티 사이 경로)"""
    G = _g()
    try:
        path = nx.shortest_path(G.to_undirected(as_view=True), source, target)
    except (nx.NetworkXNoPath, nx.NodeNotFound) as e:
        return t("경로 없음: ", "No path: ") + str(e)
    lines = []
    for a, b in zip(path, path[1:]):
        for u, v in ((a, b), (b, a)):
            for d in (G.get_edge_data(u, v) or {}).values():
                lines.append(f"{triple_text(u, v, d)} [출처 {d['doc']}]")
    return " → ".join(path) + "\n" + "\n".join(lines)


@tool
def read_document(doc_id: str) -> str:
    """Read a source document (doc01-doc19) to check evidence when the graph is not enough. (원문 읽기)"""
    docs = _docs()
    return docs[doc_id].page_content if doc_id in docs else t("없는 문서", "No such document")


TOOLS = [search_entities, get_neighbors, find_path, read_document]

_SYSTEM = {
    "ko": ("당신은 지식그래프 탐색 도구를 가진 리서치 에이전트입니다. "
           "질문의 엔티티를 search_entities 로 찾고, get_neighbors / find_path 로 관계를 따라가며, "
           "필요하면 read_document 로 원문을 확인하세요. 최종 답변에는 추론 경로와 출처 문서 id 를 포함하세요."),
    "en": ("You are a research agent with knowledge-graph tools. Find the question's entities with search_entities, "
           "follow relations with get_neighbors / find_path, and read source text with read_document when needed. "
           "Include the reasoning path and source document ids in your final answer."),
}


def system_prompt() -> str:
    return _SYSTEM[get_lang()]


SYSTEM = _SYSTEM["ko"]  # 하위 호환
