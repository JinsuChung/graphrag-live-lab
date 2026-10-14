# %% [markdown]
# # 실습 02. 기본 벡터 RAG (LangChain)  /  Lab 02. Basic vector RAG
# 문서 → 청크 분할 → 임베딩 → 벡터 저장소 → 유사도 검색 → 프롬프트 → LLM
# 수업에서 배운 LCEL 체인 그대로. 멀티홉 질문에서 어디가 부족한지 관찰한다.

# %%
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda, RunnablePassthrough

from common import get_llm, header, load_questions, t
from prompts import VECTOR_PROMPT, format_docs
from retrievers import build_vector_store

store = build_vector_store()
retriever = store.as_retriever(search_kwargs={"k": 3})
llm = get_llm()

# %% LCEL 체인 ------------------------------------------------------------
if llm:
    chain = (
        {"context": retriever | RunnableLambda(format_docs), "question": RunnablePassthrough()}
        | VECTOR_PROMPT
        | llm
        | StrOutputParser()
    )

# %% 질문 실행 ------------------------------------------------------------
for q in load_questions():
    if q["type"] == "global":
        continue
    header(f"[{q['id']} · {q['type']}] {q['question']}")
    docs = retriever.invoke(q["question"])
    got = [d.metadata["doc_id"] for d in docs]
    missing = [g for g in q["evidence"] if not any(d in got for d in g)]
    print(t("검색된 문서 :", "retrieved  :"), got)
    print(t("필요한 근거 :", "needed     :"), " + ".join("/".join(g) for g in q["evidence"]),
          t("→ 못 찾은 근거:", "→ missing:"), missing or t("없음", "none"))
    if llm:
        print(t("LLM 답변   :", "LLM answer :"), chain.invoke(q["question"]))
    else:
        print(t("(LLM_MODEL 미설정 — 검색 결과만 확인합니다)", "(LLM_MODEL not set — showing retrieval only)"))
print(t("\n관찰 포인트: 질문과 표현이 다른 '두 번째 근거 문서'를 벡터 검색이 자주 놓친다.",
        "\nObserve: vector search often misses the second evidence document whose wording differs from the question."))
