# %% [markdown]
# # 실습 08. Agentic GraphRAG — LLM 에이전트가 도구로 그래프를 탐색
# 고정 파이프라인(실습 04) 대신, LLM 이 스스로
#   "어떤 엔티티를 찾을지 → 어떤 이웃을 볼지 → 경로를 찾을지 → 원문을 읽을지"
# 를 결정한다. Think-on-Graph 아이디어의 실용 버전이며, MCP 서버로 도구를 노출하는 것도 같은 원리.
# 도구 정의는 graph_tools.py 에 있다.

# %%
from langchain.agents import create_agent

from common import get_llm, header, load_questions
from graph_tools import SYSTEM, TOOLS, find_path, get_neighbors, search_entities

# %%
llm = get_llm()
if llm is None:
    header("LLM_MODEL 미설정 — 도구만 직접 호출해 봅니다")
    print(search_entities.invoke({"keyword": "벤처캐피탈"}))
    print(get_neighbors.invoke({"entity": "똑똑한 이단아"}))
    print(find_path.invoke({"source": "저업력 중소기업", "target": "M&A 시장 활성화"}))
    raise SystemExit(0)

agent = create_agent(llm, tools=TOOLS, system_prompt=SYSTEM)

for q in load_questions():
    if q["id"] not in ("q3", "q4", "q5"):  # 근거가 여러 장에 흩어진 멀티홉 질문 위주
        continue
    header(f"[{q['id']}] {q['question']}")
    result = agent.invoke({"messages": [{"role": "user", "content": q["question"]}]})
    for m in result["messages"]:
        for call in getattr(m, "tool_calls", None) or []:
            print(f"  🔧 {call['name']}({call['args']})")
    print("\n답변:", result["messages"][-1].text)
