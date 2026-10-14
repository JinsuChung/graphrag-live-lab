"""라이브 실험실용 파이프라인 추적기.

실습 코드(lab/)의 함수를 그대로 호출하면서, 각 단계의 입력·출력·소요 시간을 '단계(step)' 목록으로 기록한다.
프론트엔드는 이 단계들을 하나씩 펼쳐 보여 준다.

step = {
  id, title, phase("인덱싱"|"검색"|"생성"), explain(설명),
  code: {file, symbol},            # "코드 보기" 버튼이 여는 위치
  view: {type, ...},               # 화면에 그릴 데이터
  graph: {...} | None,             # 오른쪽 그래프 패널 하이라이트 상태
  ms: 소요 시간
}
"""
from __future__ import annotations

import time
from contextlib import contextmanager

import numpy as np

from common import doc_by_id, evidence_recall, load_questions
from extraction import EXTRACT_PROMPT, Extraction, make_extractor, merge, normalize
from global_search import (MAP_PROMPT, REDUCE_PROMPT, Partial, community_text, detect_communities, precomputed_reports,
                           similarity_scores)
from prompts import GRAPH_PROMPT, VECTOR_PROMPT, format_docs
import retrievers as R

GOLD = {q["question"]: q for q in load_questions()}


class Trace:
    def __init__(self):
        self.steps: list[dict] = []

    @contextmanager
    def step(self, id: str, title: str, phase: str, explain: str, code: tuple[str, str] | None = None):
        s = {"id": id, "title": title, "phase": phase, "explain": explain,
             "code": {"file": code[0], "symbol": code[1]} if code else None, "view": {}, "graph": None}
        t0 = time.perf_counter()
        yield s
        s["ms"] = round((time.perf_counter() - t0) * 1000, 1)
        self.steps.append(s)


def prompt_text(prompt_value) -> str:
    return "\n\n".join(f"[{m.type}]\n{m.content}" for m in prompt_value.to_messages())


def prompt_messages(prompt_value) -> list[dict]:
    """LLM 에 그대로 보낼 메시지 목록 (답변 스트리밍 엔드포인트가 사용)."""
    role = {"human": "user", "ai": "assistant", "system": "system"}
    return [{"role": role[m.type], "content": m.content} for m in prompt_value.to_messages()]


def prompt_segments(text: str, pieces: list[dict]) -> list[dict]:
    """프롬프트 전체 문자열을 '출처별 조각'으로 나눈다 (시각화용).

    pieces = [{"kind": "context"|"triples"|"question", "label": ..., "text": ...}]
    조각이 차지하지 않는 나머지 부분은 'template'(지시문·양식)으로 표시한다.
    """
    spans, cursor = [], 0
    for p in pieces:
        i = text.find(p["text"], cursor)
        if i < 0 or not p["text"]:
            continue
        if i > cursor:
            spans.append({"kind": "template", "label": "지시문·양식", "text": text[cursor:i]})
        spans.append({**p, "text": text[i:i + len(p["text"])]})
        cursor = i + len(p["text"])
    if cursor < len(text):
        spans.append({"kind": "template", "label": "지시문·양식", "text": text[cursor:]})
    return spans


def gold_info(question: str) -> dict | None:
    q = GOLD.get(question.strip())
    return {"id": q["id"], "docs": q["supporting_docs"], "groups": q["evidence"], "answer": q["answer"]} if q else None


# ---------------------------------------------------------------------------
# 벡터 RAG
# ---------------------------------------------------------------------------
def vector_trace(question: str, k: int) -> dict:
    tr = Trace()
    docs = doc_by_id()

    with tr.step("chunk", "벡터 인덱스 (청크 + 임베딩)", "인덱싱",
                 f"문서 {len(docs)}개를 {R.CHUNK_SIZE}자(겹침 {R.CHUNK_OVERLAP}자) 단위 청크로 자르고, 각 청크를 임베딩 벡터로 "
                 "바꿔 벡터 저장소에 넣어 둔 상태입니다. 이 과정은 '문서 처리' 모드에서 단계별로 볼 수 있습니다.",
                 ("lab/retrievers.py", "build_vector_store")) as s:
        store = R.build_vector_store()
        items = list(store.store.values())
        s["view"] = {"type": "chunks", "embedding": type(store.embedding).__name__,
                     "dim": len(items[0]["vector"]), "chunk_size": R.CHUNK_SIZE, "overlap": R.CHUNK_OVERLAP,
                     "chunks": [{"doc_id": it["metadata"]["doc_id"], "len": len(it["text"]),
                                 "text": it["text"]} for it in items]}

    with tr.step("embed", "질문 임베딩", "검색",
                 "질문 문장을 같은 임베딩 모델로 벡터로 바꿉니다. 의미가 비슷한 문장일수록 벡터가 가까워집니다.",
                 ("lab/retrievers.py", "vector_search_detailed")) as s:
        qv = store.embedding.embed_query(question)
        s["view"] = {"type": "vector", "dim": len(qv), "head": [round(x, 4) for x in qv[:48]],
                     "norm": round(float(np.linalg.norm(qv)), 4)}

    with tr.step("similarity", "코사인 유사도 계산", "검색",
                 "질문 벡터와 모든 청크 벡터의 코사인 유사도를 계산합니다. 오른쪽 산점도는 고차원 벡터를 2차원으로 "
                 "줄여(PCA) 그린 것이라 거리가 대략적입니다.",
                 ("lab/retrievers.py", "vector_search_detailed")) as s:
        detail = R.vector_search_detailed(question, k)
        vecs = np.array([it["vector"] for it in items])
        mean = vecs.mean(axis=0)
        _, _, vt = np.linalg.svd(vecs - mean, full_matrices=False)
        proj = (vecs - mean) @ vt[:2].T
        qp = (np.array(qv) - mean) @ vt[:2].T
        score_of = {c["text"]: c["score"] for c in detail["chunks"]}
        s["view"] = {"type": "scores", "k": k, "chunks": detail["chunks"], "selected": detail["doc_ids"]}
        s["scatter"] = {"points": [{"doc_id": it["metadata"]["doc_id"], "x": float(p[0]), "y": float(p[1]),
                                    "score": score_of[it["text"]]} for it, p in zip(items, proj)],
                        "query": {"x": float(qp[0]), "y": float(qp[1])}, "selected": detail["doc_ids"]}

    with tr.step("topk", f"Top-{k} 문서 선택 → 컨텍스트 청크", "검색",
                 f"점수 순으로 청크를 훑으며 서로 다른 문서 {k}개가 모일 때까지의 청크 {len(detail['context'])}개를 "
                 "LLM에 줄 컨텍스트로 고릅니다.",
                 ("lab/retrievers.py", "vector_search_detailed")) as s:
        s["view"] = {"type": "docs", "doc_ids": detail["doc_ids"], "gold": gold_info(question),
                     "chunks": detail["context"]}

    with tr.step("prompt", "컨텍스트 주입 → 프롬프트 조립", "생성",
                 "고른 청크를 프롬프트 템플릿의 {context} 자리에 넣습니다. 색깔 막대는 LLM이 받는 입력에서 "
                 "지시문·각 청크·질문이 차지하는 비율입니다.",
                 ("lab/prompts.py", "VECTOR_PROMPT")) as s:
        from langchain_core.documents import Document
        ctx_docs = [Document(page_content=c["text"], metadata={"doc_id": c["doc_id"]}) for c in detail["context"]]
        pv = VECTOR_PROMPT.invoke({"context": format_docs(ctx_docs), "question": question})
        text = prompt_text(pv)
        pieces = [{"kind": "context", "label": d.metadata["doc_id"], "doc_id": d.metadata["doc_id"],
                   "text": f"[{d.metadata['doc_id']}] {d.page_content}"} for d in ctx_docs]
        pieces.append({"kind": "question", "label": "질문", "text": question})
        s["view"] = {"type": "prompt", "text": text, "chars": len(text), "segments": prompt_segments(text, pieces)}

    with tr.step("answer", "LLM 답변 (스트리밍)", "생성",
                 "조립한 프롬프트를 LLM에 보내고 답변을 토큰 단위로 받아옵니다.",
                 ("lab/02_vector_rag.py", "chain")) as s:
        s["view"] = {"type": "llm", "messages": prompt_messages(pv)}

    return {"mode": "vector", "question": question, "steps": tr.steps, "doc_ids": detail["doc_ids"]}


# ---------------------------------------------------------------------------
# 그래프 Local Search
# ---------------------------------------------------------------------------
def graph_trace(question: str, k: int) -> dict:
    tr = Trace()
    docs = doc_by_id()
    G = R.get_graph()

    with tr.step("kg", "지식그래프 준비 (인덱싱)", "인덱싱",
                 "문서에서 추출해 둔 지식그래프를 불러옵니다. 이 실습은 원문과 대조해 정리한 참조 그래프 kg.json을 기본으로 쓰고, "
                 "'그래프 구축' 탭에서 LLM이 실제로 추출하는 과정을 볼 수 있습니다.",
                 ("lab/common.py", "load_kg")) as s:
        types: dict[str, int] = {}
        for _, d in G.nodes(data=True):
            types[d["type"]] = types.get(d["type"], 0) + 1
        s["view"] = {"type": "kgstats", "nodes": G.number_of_nodes(), "edges": G.number_of_edges(), "types": types}
        s["graph"] = {"focus": []}

    with tr.step("link", "① 엔티티 연결 (Entity Linking)", "검색",
                 "질문 속 표현을 그래프 노드와 연결합니다. 여기서는 노드 이름과 별칭의 문자열 매칭을 씁니다. "
                 "실전에서는 임베딩 유사도나 LLM으로 더 유연하게 찾습니다.",
                 ("lab/retrievers.py", "link_entities_detailed")) as s:
        links = R.link_entities_detailed(question, G)
        seeds = [l["node"] for l in links]
        s["view"] = {"type": "linking", "question": question, "links": links}
        s["graph"] = {"seeds": seeds, "focus": seeds}

    with tr.step("path", "② 시드 사이 경로 탐색", "검색",
                 "찾은 엔티티가 2개 이상이면 둘을 잇는 최단 경로를 찾습니다. 질문에 이름이 나오지 않는 중간 개체가 "
                 "여기서 드러납니다 (PathRAG 아이디어)." if len(seeds) >= 2 else
                 "엔티티가 하나뿐이라 경로 탐색을 건너뜁니다. 이런 질문은 단순 그래프 검색이 약한 경우입니다.",
                 ("lab/retrievers.py", "shortest_paths")) as s:
        paths = R.shortest_paths(seeds, G)
        p_edges = [{"s": u, "t": v, "type": d["type"], "doc": d["doc"]} for u, v, d in R.edges_on_paths(paths, G)]
        edge_keys = [f"{e['s']}|{e['t']}|{e['type']}" for e in p_edges]
        s["view"] = {"type": "paths", "paths": paths, "edges": p_edges, "seeds": seeds}
        s["graph"] = {"seeds": seeds, "focus": sorted({n for p in paths for n in p}) or seeds, "edges": edge_keys}

    with tr.step("expand", "③ 1-hop 이웃 확장", "검색",
                 "시드 엔티티에 바로 연결된 이웃까지 후보를 넓힙니다. 경로 노드와 합쳐 '관련 서브그래프'가 됩니다.",
                 ("lab/retrievers.py", "expand_hops")) as s:
        hops = R.expand_hops(seeds, G, hops=1)
        sub = sorted(set(hops) | {n for p in paths for n in p})
        s["view"] = {"type": "expand", "hops": hops, "sub": sub}
        s["graph"] = {"seeds": seeds, "focus": sub, "edges": edge_keys, "near": True}

    with tr.step("ppr", "④ Personalized PageRank", "검색",
                 "시드에서 출발해 그래프를 무작위로 걷는다고 할 때 각 노드에 머무를 확률입니다. 시드와 구조적으로 "
                 "가까운 노드일수록 점수가 높습니다 (HippoRAG 아이디어). 노드 크기가 점수를 나타냅니다.",
                 ("lab/retrievers.py", "personalized_pagerank")) as s:
        ppr = R.personalized_pagerank(seeds, G) if seeds else {}
        top = sorted(ppr.items(), key=lambda x: -x[1])[:12]
        s["view"] = {"type": "ppr", "top": [{"node": n, "score": round(v, 4)} for n, v in top]}
        s["graph"] = {"seeds": seeds, "focus": sub, "weights": {n: round(v, 4) for n, v in ppr.items()}}

    with tr.step("rank", "⑤ 원문 문서 순위", "검색",
                 "경로 위 관계가 나온 문서를 1순위로, 나머지는 서브그래프 관계 양 끝 노드의 PPR 점수 합으로 정렬해 "
                 "상위 k개 원문을 고릅니다.",
                 ("lab/retrievers.py", "graph_search_detailed")) as s:
        detail = R.graph_search_detailed(question, k)  # ①~④를 묶어 문서 순위까지 계산하는 실제 검색 함수
        s["view"] = {"type": "docscores", "rows": detail["doc_scores"], "selected": detail["doc_ids"],
                     "gold": gold_info(question)}
        s["graph"] = {"seeds": seeds, "focus": sub, "edges": edge_keys}

    with tr.step("context", "⑥ 컨텍스트 구성", "생성",
                 "LLM에게 줄 재료는 두 가지입니다. 구조를 요약한 관계 트리플과, 근거가 되는 원문입니다.",
                 ("lab/04_local_graph_rag.py", "build_context")) as s:
        s["view"] = {"type": "context", "triples": detail["triples"],
                     "docs": {d: docs[d].page_content for d in detail["doc_ids"]}}

    with tr.step("prompt", "프롬프트 조립", "생성", "관계 트리플과 원문을 그래프용 프롬프트 템플릿에 넣습니다.",
                 ("lab/prompts.py", "GRAPH_PROMPT")) as s:
        triples_txt = "\n".join(detail["triples"]) or "(없음)"
        pv = GRAPH_PROMPT.invoke({"triples": triples_txt,
                                  "docs": "\n\n".join(f"[{d}] {docs[d].page_content}" for d in detail["doc_ids"]) or "(없음)",
                                  "question": question})
        text = prompt_text(pv)
        pieces = [{"kind": "triples", "label": "관계 트리플", "text": triples_txt}]
        pieces += [{"kind": "context", "label": d, "doc_id": d, "text": f"[{d}] {docs[d].page_content}"} for d in detail["doc_ids"]]
        pieces.append({"kind": "question", "label": "질문", "text": question})
        s["view"] = {"type": "prompt", "text": text, "chars": len(text), "segments": prompt_segments(text, pieces)}

    with tr.step("answer", "LLM 답변 (스트리밍)", "생성", "조립한 프롬프트를 LLM에 보내 답변을 받습니다.",
                 ("lab/04_local_graph_rag.py", "chain")) as s:
        s["view"] = {"type": "llm", "messages": prompt_messages(pv)}

    return {"mode": "graph", "question": question, "steps": tr.steps, "doc_ids": detail["doc_ids"]}


# ---------------------------------------------------------------------------
# 그래프 Global Search
# ---------------------------------------------------------------------------
def global_trace(question: str, llm) -> dict:
    tr = Trace()
    G = R.get_graph()

    with tr.step("community", "커뮤니티 탐지 (인덱싱)", "인덱싱",
                 "서로 촘촘히 연결된 노드 묶음을 찾습니다(Louvain). Microsoft GraphRAG는 이를 계층적으로(Leiden) 수행합니다. "
                 "그래프 색이 커뮤니티입니다.",
                 ("lab/global_search.py", "detect_communities")) as s:
        comms = detect_communities(G)
        s["view"] = {"type": "communities", "communities": comms}
        s["graph"] = {"color": "community", "focus": []}

    with tr.step("reports", "커뮤니티 리포트 (인덱싱)", "인덱싱",
                 "커뮤니티마다 LLM이 요약 리포트를 미리 써 둡니다. 인덱싱 비용의 큰 몫을 차지합니다. "
                 "여기서는 미리 만들어 둔 리포트(community_summaries.json)를 씁니다.",
                 ("lab/global_search.py", "community_text")) as s:
        reports = precomputed_reports()
        s["view"] = {"type": "reports", "reports": reports,
                     "input_example": community_text(G, reports[0]["members"])}
        s["graph"] = {"color": "community", "focus": []}

    with tr.step("map", "Map: 리포트마다 부분 답변", "검색",
                 ("각 리포트에 질문을 던져 '부분 답변 + 관련도 점수'를 받습니다 (LLM 호출이 리포트 수만큼 병렬로 일어남)."
                  if llm else
                  "LLM이 없어서 '질문과 리포트의 임베딩 유사도'로 관련도를 흉내 내고, 리포트 요약을 부분 답변 대신 씁니다. "
                  "LLM이 있으면 각 리포트에 질문을 던져 부분 답변과 점수를 받습니다."),
                 ("lab/global_search.py", "MAP_PROMPT")) as s:
        rows = []
        if llm:
            chain = MAP_PROMPT | llm.with_structured_output(Partial, method="json_schema")
            outs = chain.batch([{"report": f"{r['title']}\n{r['summary']}", "question": question} for r in reports])
            for r, p in zip(reports, outs):
                rows.append({"id": r["id"], "title": r["title"], "score": p.score, "answer": p.answer, "by": "LLM"})
        else:
            scores = similarity_scores(question, [f"{r['title']}\n{r['summary']}" for r in reports],
                                       R.build_vector_store().embedding)
            for r, sc in zip(reports, scores):
                rows.append({"id": r["id"], "title": r["title"], "score": sc,
                             "answer": r["summary"], "by": "임베딩 유사도 상대 점수 (LLM 대체)"})
        rows.sort(key=lambda x: -x["score"])
        s["view"] = {"type": "map", "rows": rows}
        s["graph"] = {"color": "community", "communityScores": {str(r["id"]): r["score"] for r in rows}}

    with tr.step("reduce", "Reduce: 부분 답변 종합 프롬프트", "생성",
                 "점수가 높은 부분 답변만 모아 최종 답변을 쓰게 합니다.",
                 ("lab/global_search.py", "REDUCE_PROMPT")) as s:
        kept = [r for r in rows if r["score"] > 0 and r["answer"]]
        partial_lines = [f"({r['score']}) {r['answer']}" for r in kept]
        pv = REDUCE_PROMPT.invoke({"partials": "\n".join(partial_lines), "question": question})
        text = prompt_text(pv)
        pieces = [{"kind": "context", "label": f"C{r['id']}", "community": r["id"], "text": line}
                  for r, line in zip(kept, partial_lines)]
        pieces.append({"kind": "question", "label": "질문", "text": question})
        s["view"] = {"type": "prompt", "text": text, "chars": len(text), "segments": prompt_segments(text, pieces)}

    with tr.step("answer", "LLM 답변 (스트리밍)", "생성", "종합 답변을 생성합니다.",
                 ("lab/05_global_graph_rag.py", "reduce_chain")) as s:
        s["view"] = {"type": "llm", "messages": prompt_messages(pv)}

    return {"mode": "global", "question": question, "steps": tr.steps}


# ---------------------------------------------------------------------------
# 비교
# ---------------------------------------------------------------------------
def compare(question: str, k: int) -> dict:
    v_detail = R.vector_search_detailed(question, k)
    v = v_detail["doc_ids"]
    g_detail = R.graph_search_detailed(question, k)
    g = g_detail["doc_ids"]
    h = R.interleave(g, v, k)
    gold = gold_info(question)

    def rec(ids):
        return round(evidence_recall(ids, gold["groups"]), 2) if gold else None
    docs = doc_by_id()
    from langchain_core.documents import Document
    ctx = [Document(page_content=c["text"], metadata={"doc_id": c["doc_id"]}) for c in v_detail["context"]]
    vp = prompt_messages(VECTOR_PROMPT.invoke({"context": format_docs(ctx), "question": question}))
    gp = prompt_messages(GRAPH_PROMPT.invoke({"triples": "\n".join(g_detail["triples"]) or "(없음)",
                                          "docs": "\n\n".join(f"[{d}] {docs[d].page_content}" for d in g) or "(없음)",
                                          "question": question}))
    graph = {"seeds": g_detail["seeds"], "focus": g_detail["sub"], "near": True,
             "edges": [f"{e['s']}|{e['t']}|{e['type']}" for e in g_detail["path_edges"]]}
    return {"question": question, "gold": gold, "seeds": g_detail["seeds"], "graph": graph,
            "rows": [{"method": "vector", "docs": v, "recall": rec(v), "messages": vp},
                     {"method": "graph", "docs": g, "recall": rec(g), "messages": gp},
                     {"method": "hybrid", "docs": h, "recall": rec(h)}]}


def benchmark(k: int) -> dict:
    rows = []
    for q in load_questions():
        if q["type"] == "global":
            continue
        c = compare(q["question"], k)
        rows.append({"id": q["id"], "type": q["type"], "question": q["question"],
                     **{r["method"]: {"docs": r["docs"], "recall": r["recall"]} for r in c["rows"]}})
    avg = {m: round(sum(r[m]["recall"] for r in rows) / len(rows), 2) for m in ("vector", "graph", "hybrid")}
    return {"k": k, "rows": rows, "avg": avg}


# ---------------------------------------------------------------------------
# 그래프 구축 (추출 + 엔티티 해소)
# ---------------------------------------------------------------------------
def extract_trace(doc_id: str | None, text: str | None, llm) -> dict:
    tr = Trace()
    docs = doc_by_id()
    G = R.get_graph()
    src = text.strip() if text and text.strip() else docs[doc_id].page_content
    label = doc_id if not (text and text.strip()) else "직접 입력"

    with tr.step("input", "입력 문서", "인덱싱", "그래프로 만들 원문입니다. 실제 시스템에서는 청크 단위로 이 과정을 반복합니다.",
                 None) as s:
        s["view"] = {"type": "text", "label": label, "text": src}

    with tr.step("prompt", "추출 프롬프트 + 출력 스키마", "인덱싱",
                 "LLM에게 '엔티티와 관계를 이 JSON 스키마대로 내놓으라'고 요청합니다. LangChain의 with_structured_output이 "
                 "Pydantic 모델을 JSON 스키마로 바꿔 모델의 구조화 출력 기능에 넘깁니다.",
                 ("lab/extraction.py", "Extraction")) as s:
        s["view"] = {"type": "prompt", "text": prompt_text(EXTRACT_PROMPT.invoke({"text": src})),
                     "schema": Extraction.model_json_schema()}

    with tr.step("extract", "LLM 추출 결과", "인덱싱",
                 "모델이 돌려준 구조화된 결과입니다." if llm else
                 "LLM이 설정되지 않아, 이 문서에 대한 참조 그래프(kg.json)의 해당 부분을 대신 보여 줍니다. "
                 ".env에 LLM_MODEL을 설정하면 실제 추출 결과가 나옵니다.",
                 ("lab/extraction.py", "make_extractor")) as s:
        if llm:
            ex: Extraction = make_extractor(llm).invoke({"text": src})
            by = "LLM"
        else:
            ents = {n: d for n, d in G.nodes(data=True) if doc_id in d.get("docs", [])}
            rels = [(u, v, d) for u, v, d in G.edges(data=True) if d["doc"] == doc_id]
            for u, v, _ in rels:
                ents.setdefault(u, G.nodes[u]); ents.setdefault(v, G.nodes[v])
            ex = Extraction.model_validate({
                "entities": [{"name": n, "type": d["type"], "description": d["description"]} for n, d in ents.items()],
                "relations": [{"source": u, "type": d["type"], "target": v, "description": d["description"]}
                              for u, v, d in rels]})
            by = "정답 그래프(kg.json)"
        s["view"] = {"type": "extraction", "by": by, **ex.model_dump()}
        s["graph"] = {"mini": {"nodes": [e.name for e in ex.entities],
                               "edges": [{"s": r.source, "t": r.target, "type": r.type} for r in ex.relations]}}

    with tr.step("resolve", "엔티티 해소 (기존 그래프와 병합)", "인덱싱",
                 "새로 뽑은 엔티티 이름을 정규화(공백·기호 제거, 소문자)해 기존 그래프의 이름·별칭과 비교합니다. "
                 "같으면 기존 노드에 합치고, 없으면 새 노드로 추가합니다. 엔티티 목록에 없는 이름을 가리키는 관계는 버립니다.",
                 ("lab/extraction.py", "merge")) as s:
        index = {}
        for n, d in G.nodes(data=True):
            for name in [n, *d.get("aliases", [])]:
                index[normalize(name)] = n
        rows = [{"name": e.name, "key": normalize(e.name), "match": index.get(normalize(e.name))} for e in ex.entities]
        merged = merge({label: ex})
        s["view"] = {"type": "resolution", "rows": rows, "dropped": merged["dropped"]}
        s["graph"] = {"focus": sorted({r["match"] for r in rows if r["match"]})}

    return {"mode": "extract", "steps": tr.steps}


# ---------------------------------------------------------------------------
# 문서 처리 (PDF → 정제 → 섹션 → 청크 → 임베딩 → 저장)
# ---------------------------------------------------------------------------
_PAGES: list[str] | None = None
_SECTIONS: list[dict] | None = None


def _pdf():
    global _PAGES, _SECTIONS
    if _PAGES is None:
        from pdf_prep import load_pages, split_sections
        _PAGES = load_pages()
        _SECTIONS = split_sections(_PAGES)
    return _PAGES, _SECTIONS


def chunk_view(doc_id: str, chunk_size: int, overlap: int) -> dict:
    """선택 문서의 청크 경계(시작·끝 위치)와 전체 문서 기준 통계."""
    splitter = R.make_splitter(chunk_size, overlap)
    docs = doc_by_id()
    text = docs[doc_id].page_content
    chunks = splitter.create_documents([text])
    spans = [{"start": c.metadata["start_index"], "end": c.metadata["start_index"] + len(c.page_content),
              "len": len(c.page_content)} for c in chunks]
    all_lens = [len(c.page_content) for d in docs.values() for c in splitter.create_documents([d.page_content])]
    return {"type": "chunking", "doc_id": doc_id, "title": docs[doc_id].metadata["title"], "text": text,
            "chunk_size": chunk_size, "overlap": overlap, "spans": spans,
            "total": len(all_lens), "avg": round(sum(all_lens) / len(all_lens)), "lens": all_lens,
            "index_chunk_size": R.CHUNK_SIZE, "index_overlap": R.CHUNK_OVERLAP}


def ingest_trace(page: int, doc_id: str, chunk_size: int, overlap: int) -> dict:
    from collections import Counter

    from pdf_prep import PAGE_OFFSET, PDF_PATH, annotate_page
    tr = Trace()

    with tr.step("load", "① PDF 로드", "인덱싱",
                 "LangChain의 PyPDFLoader가 PDF를 페이지마다 하나의 Document로 읽습니다. 표·차트가 있는 페이지는 "
                 "숫자와 라벨이 텍스트로 섞여 나옵니다. 막대를 누르면 해당 페이지를 봅니다.",
                 ("lab/pdf_prep.py", "load_pages")) as s:
        pages, sections = _pdf()
        s["view"] = {"type": "pages", "file": PDF_PATH.name, "offset": PAGE_OFFSET, "page": page,
                     "chars": [len(p) for p in pages], "text": pages[page]}

    with tr.step("clean", "② 정제 (잡음 제거)", "인덱싱",
                 "규칙으로 차트 숫자·머리글·각주 등을 지웁니다. 취소선이 지운 줄이고, 오른쪽 배지가 지운 이유입니다. "
                 "규칙이 완벽하지 않다는 점도 함께 보세요.",
                 ("lab/pdf_prep.py", "annotate_page")) as s:
        total = Counter()
        for p in pages:
            total.update(a["reason"] or "남김" for a in annotate_page(p))
        s["view"] = {"type": "cleaning", "page": page, "offset": PAGE_OFFSET,
                     "lines": annotate_page(pages[page]), "totals": dict(total.most_common())}

    with tr.step("sections", "③ 섹션 분할 (주제별 문서)", "인덱싱",
                 "보고서의 문단 번호(1~56)와 BOX를 기준으로 주제가 같은 문단을 묶어 문서 19개를 만듭니다. "
                 "문서마다 출처(문단·쪽)를 메타데이터로 남겨 나중에 근거를 보여 줄 수 있게 합니다.",
                 ("lab/pdf_prep.py", "split_sections")) as s:
        s["view"] = {"type": "sections", "selected": doc_id,
                     "docs": [{"doc_id": d["doc_id"], "title": d["title"], "where": d["where"], "chars": len(d["text"])}
                              for d in sections]}

    with tr.step("chunk", "④ 청크 분할", "인덱싱",
                 "문서를 검색 단위인 청크로 자릅니다. RecursiveCharacterTextSplitter는 문단 → 줄 → 공백 순으로 자를 곳을 "
                 "찾습니다. 크기·겹침을 바꾸면 경계가 바로 다시 계산됩니다. 겹침(진한 부분)은 문장이 잘려 의미를 잃는 것을 막습니다.",
                 ("lab/retrievers.py", "make_splitter")) as s:
        s["view"] = chunk_view(doc_id, chunk_size, overlap)

    with tr.step("embed", "⑤ 임베딩", "인덱싱",
                 "청크마다 임베딩 모델이 고정 길이 숫자 벡터를 만듭니다. 아래 히트맵의 한 줄이 청크 하나의 벡터(앞부분)입니다. "
                 "오른쪽 산점도는 전체 청크를 2차원으로 줄여 문서(색)별로 그린 것으로, 같은 주제의 청크가 가까이 모입니다.",
                 ("lab/retrievers.py", "build_vector_store")) as s:
        store = R.build_vector_store()
        items = list(store.store.values())
        mine = [it for it in items if it["metadata"]["doc_id"] == doc_id]
        vecs = np.array([it["vector"] for it in items])
        mean = vecs.mean(axis=0)
        _, _, vt = np.linalg.svd(vecs - mean, full_matrices=False)
        proj = (vecs - mean) @ vt[:2].T
        s["view"] = {"type": "embedding", "doc_id": doc_id, "model": type(store.embedding).__name__,
                     "dim": len(items[0]["vector"]),
                     "rows": [{"text": it["text"][:60], "v": [round(x, 3) for x in it["vector"][:48]]} for it in mine]}
        s["scatter"] = {"points": [{"doc_id": it["metadata"]["doc_id"], "x": float(p[0]), "y": float(p[1])}
                                   for it, p in zip(items, proj)], "focus": doc_id}

    with tr.step("store", "⑥ 벡터 저장소", "인덱싱",
                 "청크 원문, 메타데이터, 벡터를 한 레코드로 저장합니다. 질문이 오면 이 저장소에서 가장 가까운 벡터를 찾습니다. "
                 "실습은 메모리(InMemoryVectorStore)를 쓰고, 실서비스는 Chroma·FAISS·pgvector·Neo4j 벡터 인덱스 등을 씁니다.",
                 ("lab/retrievers.py", "build_vector_store")) as s:
        it = mine[0] if mine else items[0]
        s["view"] = {"type": "store", "count": len(items), "dim": len(it["vector"]),
                     "bytes": len(items) * len(it["vector"]) * 8,
                     "sample": {"id": it["id"], "metadata": it["metadata"], "text": it["text"][:160] + "…",
                                "vector": [round(x, 4) for x in it["vector"][:6]] + ["…"]}}

    return {"mode": "ingest", "steps": tr.steps}
