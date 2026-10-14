"""LLM 기반 지식그래프 추출 + 엔티티 해소 (실습 03, 라이브 실험실 공용)."""
from __future__ import annotations

import re

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from prompts import ByLang

ENTITY_TYPES = ["Organization", "Person", "Product", "Event", "Technology", "Policy", "Location", "Concept"]


class Entity(BaseModel):
    name: str = Field(description="엔티티의 대표 이름 (문서에 나온 표기 그대로) / canonical entity name as written in the document")
    type: str = Field(description=f"다음 중 하나 / one of: {', '.join(ENTITY_TYPES)}")
    description: str = Field(description="문서에 근거한 한 문장 설명 / one-sentence description grounded in the document")


class Relation(BaseModel):
    source: str = Field(description="관계의 주어 엔티티 이름 / subject entity name")
    type: str = Field(description="관계 이름, 영어 대문자 스네이크 케이스 / relation name in UPPER_SNAKE_CASE (e.g. CAUSES, IMPROVES)")
    target: str = Field(description="관계의 목적어 엔티티 이름 / object entity name")
    description: str = Field(description="관계를 뒷받침하는 짧은 설명 / short supporting description")


class Extraction(BaseModel):
    entities: list[Entity]
    relations: list[Relation]


EXTRACT_PROMPT = ByLang(
    ko=ChatPromptTemplate.from_messages([
        ("system",
         "당신은 문서에서 지식그래프를 추출하는 도우미입니다. 문서에 명시된 사실만 추출하세요. "
         "추측하지 마세요. relations 의 source/target 은 반드시 entities 의 name 중 하나여야 합니다."),
        ("human", "# 문서\n{text}"),
    ]),
    en=ChatPromptTemplate.from_messages([
        ("system",
         "You extract a knowledge graph from a document. Extract only facts stated in the document; do not guess. "
         "Every relation's source/target must be one of the entity names. Write names in English as in the text."),
        ("human", "# Document\n{text}"),
    ]),
)


def make_extractor(llm):
    # method="json_schema": 모델의 네이티브 구조화 출력 사용 (Anthropic/OpenAI 모두 지원)
    return EXTRACT_PROMPT | llm.with_structured_output(Extraction, method="json_schema")


def normalize(name: str) -> str:
    """아주 단순한 정규화: 공백·특수문자 제거 + 소문자. 실전에서는 임베딩 유사도나 LLM 판정을 더한다."""
    return re.sub(r"[\s\-_'\"()]", "", name).lower()


def merge(extractions: dict[str, Extraction]) -> dict:
    """문서별 추출 결과를 하나의 그래프로 합친다 (엔티티 해소 포함)."""
    nodes: dict[str, dict] = {}      # 정규화 키 → 노드
    canonical: dict[str, str] = {}   # 정규화 키 → 대표 이름
    edges, dropped = [], []
    for doc_id, ex in extractions.items():
        for e in ex.entities:
            key = normalize(e.name)
            if key not in nodes:
                canonical[key] = e.name
                nodes[key] = {"id": e.name, "type": e.type, "description": e.description, "aliases": [], "docs": []}
            node = nodes[key]
            if e.name != node["id"] and e.name not in node["aliases"]:
                node["aliases"].append(e.name)
            if doc_id not in node["docs"]:
                node["docs"].append(doc_id)
        for r in ex.relations:
            s, t = canonical.get(normalize(r.source)), canonical.get(normalize(r.target))
            if s and t:
                edges.append({"source": s, "type": r.type, "target": t, "description": r.description, "doc": doc_id})
            else:  # 엔티티 목록에 없는 이름을 가리키면 버린다 (LLM 환각 방지)
                dropped.append(f"{r.source} -[{r.type}]-> {r.target}")
    return {"nodes": list(nodes.values()), "edges": edges, "dropped": dropped}


# ---------------------------------------------------------------------------
# 교과서 방식: LangChain LLMGraphTransformer
# ---------------------------------------------------------------------------
def lgt_extract(llm, docs, allowed_nodes=None, allowed_relationships=None, concurrency: int = 6) -> dict:
    """langchain-experimental 의 LLMGraphTransformer 로 추출해 kg.json 형식으로 돌려준다.

    allowed_nodes / allowed_relationships 를 주면 '스키마 기반 추출', 비우면 '자유 추출'.
    (langchain-experimental 은 유지보수 종료 예정이라 경고가 뜰 수 있다)
    """
    from langchain_experimental.graph_transformers import LLMGraphTransformer
    transformer = LLMGraphTransformer(llm=llm, allowed_nodes=allowed_nodes or [],
                                      allowed_relationships=allowed_relationships or [],
                                      node_properties=["description"])
    # 문서마다 한 번씩 호출된다. Runnable.batch 로 여러 문서를 동시에 처리한다.
    from langchain_core.runnables import RunnableLambda
    graph_docs = RunnableLambda(lambda d: transformer.process_response(d)).batch(
        list(docs), config={"max_concurrency": concurrency})
    nodes: dict[str, dict] = {}
    edges = []
    for doc, gd in zip(docs, graph_docs):
        doc_id = doc.metadata["doc_id"]
        for n in gd.nodes:
            node = nodes.setdefault(normalize(str(n.id)), {"id": str(n.id), "type": n.type,
                                                            "description": n.properties.get("description", ""),
                                                            "aliases": [], "docs": []})
            if doc_id not in node["docs"]:
                node["docs"].append(doc_id)
        for r in gd.relationships:
            edges.append({"source": str(r.source.id), "type": r.type, "target": str(r.target.id),
                          "description": "", "doc": doc_id})
    return {"nodes": list(nodes.values()), "edges": edges, "dropped": []}


# ---------------------------------------------------------------------------
# LLM 이 만든 그래프 vs 참조 그래프 (kg.json)
# ---------------------------------------------------------------------------
def compare_graphs(pred: dict, ref: dict) -> dict:
    """노드·관계가 얼마나 겹치는지 계산한다.

    - 노드: 이름·별칭을 정규화해 같으면 일치로 본다.
    - 관계: 양 끝 노드가 모두 일치하고 참조 그래프에 두 노드 사이 관계가 있으면(방향·관계 이름 무시) 일치.
    참조 그래프(kg.json)는 핵심 관계만 담았으므로, '참조에 없음'이 곧 '틀림'은 아니다.
    """
    ref_index = {}
    for n in ref["nodes"]:
        for name in [n["id"], *n.get("aliases", [])]:
            ref_index[normalize(name)] = n["id"]
    to_ref = {n["id"]: ref_index.get(normalize(n["id"])) for n in pred["nodes"]}
    matched_nodes = {r for r in to_ref.values() if r}
    ref_pairs = {frozenset((e["source"], e["target"])) for e in ref["edges"]}
    hit_edges, extra_edges = [], []
    covered = set()
    for e in pred["edges"]:
        s, t = to_ref.get(e["source"]) or ref_index.get(normalize(e["source"])), \
               to_ref.get(e["target"]) or ref_index.get(normalize(e["target"]))
        pair = frozenset((s, t)) if s and t else None
        if pair and pair in ref_pairs:
            hit_edges.append(e); covered.add(pair)
        else:
            extra_edges.append(e)
    missed = [e for e in ref["edges"] if frozenset((e["source"], e["target"])) not in covered]
    return {
        "pred_nodes": len(pred["nodes"]), "pred_edges": len(pred["edges"]),
        "ref_nodes": len(ref["nodes"]), "ref_edges": len(ref["edges"]),
        "node_recall": round(len(matched_nodes) / len(ref["nodes"]), 2),
        "edge_recall": round(len(covered) / len(ref_pairs), 2),
        "edge_in_ref_ratio": round(len(hit_edges) / max(1, len(pred["edges"])), 2),
        "relation_types": len({e["type"] for e in pred["edges"]}),
        "missed_examples": [f"{e['source']} -[{e['type']}]-> {e['target']} ({e['doc']})" for e in missed[:10]],
        "extra_examples": [f"{e['source']} -[{e['type']}]-> {e['target']} ({e['doc']})" for e in extra_edges[:10]],
    }
