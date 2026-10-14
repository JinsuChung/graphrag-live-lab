# %% [markdown]
# # 실습 07. Neo4j 그래프 DB + Text2Cypher (선택 실습)
# 준비 (둘 중 하나, .env 의 NEO4J_* 값만 바꾸면 코드는 그대로):
#   (A) 로컬:  프로젝트 루트에서 docker compose up -d   → http://localhost:7474 (Neo4j Browser)
#   (B) AuraDB: https://console.neo4j.io 에서 무료 인스턴스 생성 → .env 에 neo4j+s:// URI 와 비밀번호
# ① kg.json 을 Neo4j 에 적재 (MERGE)
# ② Cypher 로 직접 질의 (경로 탐색, 집계)
# ③ GraphCypherQAChain: 자연어 → Cypher 생성 → 실행 → 답변

# %%
import json
import os
import re

from langchain_neo4j import GraphCypherQAChain, Neo4jGraph

from common import DATA, get_llm, header

graph = Neo4jGraph(
    url=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
    username=os.getenv("NEO4J_USERNAME", "neo4j"),
    password=os.getenv("NEO4J_PASSWORD", ""),
    database=os.getenv("NEO4J_DATABASE", "neo4j"),
)

# %% ① 적재 --------------------------------------------------------------
kg = json.loads((DATA / os.getenv("KG_FILE", "kg.json")).read_text(encoding="utf-8"))
SAFE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")  # 라벨/관계 타입은 파라미터화가 안 되므로 검증 후 삽입

# 이 실습이 만든 노드(:Entity)만 지운다 — 교과서 실습 데이터가 같은 DB(특히 Aura)에 있어도 안전
graph.query("MATCH (n:Entity) DETACH DELETE n")
for n in kg["nodes"]:
    assert SAFE.match(n["type"]), n["type"]
    graph.query(
        f"MERGE (e:Entity:{n['type']} {{id: $id}}) SET e.description = $desc, e.aliases = $aliases",
        {"id": n["id"], "desc": n["description"], "aliases": n.get("aliases", [])},
    )
for e in kg["edges"]:
    assert SAFE.match(e["type"]), e["type"]
    graph.query(
        f"MATCH (a:Entity {{id: $s}}), (b:Entity {{id: $t}}) "
        f"MERGE (a)-[r:{e['type']}]->(b) SET r.description = $d, r.doc = $doc",
        {"s": e["source"], "t": e["target"], "d": e["description"], "doc": e["doc"]},
    )
graph.refresh_schema()
header("그래프 스키마 (LLM 이 Cypher 를 만들 때 참고하는 정보)")
print(graph.schema)

# %% ② 직접 Cypher -------------------------------------------------------
header("Cypher: 저업력 중소기업 → 기초연구 선별 지원 최단 경로")
rows = graph.query(
    "MATCH p = shortestPath((a:Entity {id:'저업력 중소기업'})-[*..6]-(b:Entity {id:'기초연구 선별 지원'})) "
    "RETURN [n IN nodes(p) | n.id] AS nodes, [r IN relationships(p) | type(r)] AS rels"
)
print(rows)

header("Cypher: 가장 많이 연결된 엔티티 Top 5")
print(graph.query(
    "MATCH (n:Entity)-[r]-() RETURN n.id AS entity, count(r) AS degree ORDER BY degree DESC LIMIT 5"
))

# %% ③ Text2Cypher -------------------------------------------------------
llm = get_llm()
if llm is None:
    print("\n(LLM_MODEL 미설정 — Text2Cypher 는 건너뜁니다)")
    raise SystemExit(0)

chain = GraphCypherQAChain.from_llm(
    llm,
    graph=graph,
    validate_cypher=True,           # 관계 방향 오류 자동 교정
    return_intermediate_steps=True,  # 생성된 Cypher 확인용
    allow_dangerous_requests=True,   # LLM 이 만든 쿼리를 DB 에 실행한다는 점을 명시적으로 동의 (읽기 전용 계정 권장)
)
for q in ["대기업이 겪는 문제는 뭐야?", "민간 벤처캐피탈의 유형을 모두 알려줘", "사회후생을 높이는 정책은 무엇이 있어?"]:
    header(q)
    out = chain.invoke({"query": q})
    print("생성된 Cypher:", out["intermediate_steps"][0]["query"])
    print("답변:", out["result"])
