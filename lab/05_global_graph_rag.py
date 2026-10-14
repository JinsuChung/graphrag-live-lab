# %% [markdown]
# # 실습 05. 그래프 RAG — Global Search (Microsoft GraphRAG 방식)  /  Lab 05. Global search
# 인덱싱: 커뮤니티 탐지 → 커뮤니티별 요약(Community Report) 미리 생성
# 질의  : Map(요약마다 부분 답변 + 중요도 점수) → Reduce(점수 높은 부분 답변을 종합)
# "전체 문서의 주제/구조/위험은?" 같은 질문은 Top-k 청크 검색으로는 답하기 어렵다.
# 핵심 구현은 global_search.py 에 있다.

# %%
from langchain_core.output_parsers import StrOutputParser

from common import get_llm, header, load_kg, load_questions, t
from global_search import (MAP_PROMPT, REDUCE_PROMPT, REPORT_PROMPT, Partial, Report, community_text,
                           detect_communities, precomputed_reports)

G = load_kg()
llm = get_llm()

# %% 1) 커뮤니티 탐지 → 2) 커뮤니티 요약 (인덱싱 단계, 가장 비싼 부분) ---------
communities = detect_communities(G)
if llm:
    report_chain = REPORT_PROMPT | llm.with_structured_output(Report, method="json_schema")
    reports = []
    for i, members in enumerate(communities):
        r = report_chain.invoke({"text": community_text(G, members)})
        reports.append({"id": i, "members": members, **r.model_dump()})
else:
    print(t("(LLM_MODEL 미설정 — 미리 만든 커뮤니티 리포트를 사용합니다)", "(LLM_MODEL not set — using the prepared community reports)"))
    reports = precomputed_reports()

header(t("커뮤니티 보고서", "Community reports"))
for r in reports:
    print(f"\n[C{r['id']}] {r['title']}  ({t('중요도', 'rating')} {r['rating']})")
    print(t("  구성:", "  members:"), ", ".join(r["members"]))
    print(t("  요약:", "  summary:"), r["summary"])

# %% 3) Map-Reduce 질의 --------------------------------------------------
question = next(q for q in load_questions() if q["type"] == "global")["question"]
header(t("Global 질문: ", "Global question: ") + question)

if not llm:
    print(t("LLM 이 있으면 아래 순서로 동작합니다:\n"
            " Map   : 각 커뮤니티 요약에 질문을 던져 '부분 답변 + 관련도 점수(0~100)'를 받음\n"
            " Reduce: 점수 높은 부분 답변들을 모아 최종 답변을 작성",
            "With an LLM this runs as:\n"
            " Map   : ask each community report for a partial answer + relevance score (0-100)\n"
            " Reduce: combine the highest-scoring partial answers into the final answer"))
    raise SystemExit(0)

map_chain = MAP_PROMPT | llm.with_structured_output(Partial, method="json_schema")
partials = []
for r in reports:
    p = map_chain.invoke({"report": f"{r['title']}\n{r['summary']}", "question": question})
    print(f"  Map C{r['id']} → {t('점수', 'score')} {p.score}")
    if p.score > 0 and p.answer:
        partials.append((p.score, p.answer))

partials.sort(reverse=True)
reduce_chain = REDUCE_PROMPT | llm | StrOutputParser()
header(t("Reduce → 최종 답변", "Reduce → final answer"))
print(reduce_chain.invoke({"partials": "\n".join(f"({s}) {a}" for s, a in partials), "question": question}))
