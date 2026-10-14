"""에이전트용 그래프 탐색 도구 (실습 08, 라이브 실험실 공용)."""
import networkx as nx
from langchain_core.tools import tool

from common import doc_by_id, triple_text
from retrievers import get_graph

G = get_graph()
U = G.to_undirected(as_view=True)
DOCS = doc_by_id()


@tool
def search_entities(keyword: str) -> str:
    """키워드가 이름·별칭·설명에 포함된 그래프 엔티티를 찾는다. 탐색의 시작점을 정할 때 사용."""
    hits = [
        f"{n} ({d['type']}): {d['description']}"
        for n, d in G.nodes(data=True)
        if keyword in n or any(keyword in a for a in d.get("aliases", [])) or keyword in d["description"]
    ]
    return "\n".join(hits) or "결과 없음"


@tool
def get_neighbors(entity: str) -> str:
    """엔티티에 연결된 모든 관계(나가는/들어오는 엣지)를 트리플로 보여 준다. 출처 문서 id 포함."""
    if entity not in G:
        return f"'{entity}' 노드가 없습니다. search_entities 로 정확한 이름을 먼저 찾으세요."
    edges = list(G.out_edges(entity, data=True)) + list(G.in_edges(entity, data=True))
    return "\n".join(f"{triple_text(u, v, d)} [출처 {d['doc']}]" for u, v, d in edges)


@tool
def find_path(source: str, target: str) -> str:
    """두 엔티티 사이의 최단 연결 경로를 찾는다. 인과 관계나 간접 연결을 확인할 때 사용."""
    try:
        path = nx.shortest_path(U, source, target)
    except (nx.NetworkXNoPath, nx.NodeNotFound) as e:
        return f"경로 없음: {e}"
    lines = []
    for a, b in zip(path, path[1:]):
        for u, v in ((a, b), (b, a)):
            for d in (G.get_edge_data(u, v) or {}).values():
                lines.append(f"{triple_text(u, v, d)} [출처 {d['doc']}]")
    return " → ".join(path) + "\n" + "\n".join(lines)


@tool
def read_document(doc_id: str) -> str:
    """원문 문서(doc01 ~ doc19)를 읽는다. 그래프 정보만으로 부족할 때 근거 확인용."""
    return DOCS[doc_id].page_content if doc_id in DOCS else "없는 문서"


TOOLS = [search_entities, get_neighbors, find_path, read_document]

SYSTEM = (
    "당신은 지식그래프 탐색 도구를 가진 리서치 에이전트입니다. "
    "질문의 엔티티를 search_entities 로 찾고, get_neighbors / find_path 로 관계를 따라가며, "
    "필요하면 read_document 로 원문을 확인하세요. 최종 답변에는 추론 경로와 출처 문서 id 를 포함하세요."
)
