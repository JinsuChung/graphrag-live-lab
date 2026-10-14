# %% [markdown]
# # 실습 04. 그래프 RAG — Local Search  /  Lab 04. Graph RAG — local search
# ① Entity Linking: 질문 속 엔티티를 그래프 노드와 연결
# ② 경로 탐색 + 1-hop 이웃 확장 → 관련 서브그래프
# ③ Personalized PageRank 로 중요도 계산 → 원문 문서 순위화
# ④ [트리플 + 원문]을 컨텍스트로 LLM 에 전달
# 핵심 구현은 retrievers.py 의 graph_retrieve() 에 있다.

# %%
from langchain_core.output_parsers import StrOutputParser

from common import doc_by_id, get_llm, header, load_questions, t
from prompts import GRAPH_PROMPT
from retrievers import graph_retrieve

DOCS = doc_by_id()
llm = get_llm()
chain = (GRAPH_PROMPT | llm | StrOutputParser()) if llm else None


def build_context(question: str, k: int = 4) -> dict:
    doc_ids, seeds, triples = graph_retrieve(question, k=k, return_context=True)
    return {
        "question": question,
        "seeds": seeds,
        "doc_ids": doc_ids,
        "triples": "\n".join(triples),
        "docs": "\n\n".join(f"[{d}] {DOCS[d].page_content}" for d in doc_ids),
    }


# %%
for q in load_questions():
    if q["type"] == "global":
        continue
    header(f"[{q['id']} · {q['type']}] {q['question']}")
    ctx = build_context(q["question"])
    print(t("① 연결된 엔티티 :", "① linked entities:"), ctx["seeds"])
    print(t("② 관계 트리플   :", "② triples        :"))
    for tr in ctx["triples"].splitlines()[:8]:
        print("     ", tr)
    print(t("③ 선택된 원문   :", "③ chosen docs    :"), ctx["doc_ids"], t("/ 정답 근거:", "/ evidence:"), " + ".join("/".join(g) for g in q["evidence"]))
    if chain:
        print(t("④ LLM 답변      :", "④ LLM answer     :"), chain.invoke(ctx))

print(t("\n관찰 포인트:\n"
        " - q3 처럼 질문 속 두 엔티티(저업력 중소기업, 벤처캐피탈 접근성)를 잇는 근거는 그래프 경로가 잘 찾는다.\n"
        " - q5 처럼 '결론에서 권고한 유형'처럼 엔티티 이름 없이 근거를 가리키면, 문자열 매칭 기반 엔티티 연결이 놓친다.\n"
        "   → 해결책: LLM 이 질문을 해석해 관계를 골라 가며 탐색 (Think-on-Graph / 실습 08 Agentic)",
        "\nObserve:\n"
        " - Like q3, when two entities in the question (young SMEs, VC accessibility) must be linked, graph paths work well.\n"
        " - Like q5, when evidence is referred to without entity names ('types recommended in the conclusion'),\n"
        "   string-matching entity linking fails → let an LLM interpret the question and choose relations (lab 08)."))
