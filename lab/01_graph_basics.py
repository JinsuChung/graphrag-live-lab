# %% [markdown]
# # 실습 01. 그래프 기초 (networkx)  /  Lab 01. Graph basics
# - 노드(Node)와 엣지(Edge), 방향/무방향, 이웃, 차수(degree)  / nodes, edges, neighbors, degree
# - 경로 탐색(BFS, 최단 경로) = 멀티홉 추론의 기본 연산          / paths = the core of multi-hop reasoning
# - 중심성(PageRank)과 Personalized PageRank = HippoRAG 의 핵심 / (personalized) PageRank
# - 커뮤니티 탐지(Louvain) = Microsoft GraphRAG 의 Global Search 재료 / community detection
# LLM/API 키 없이 실행된다. / Runs without an LLM.

# %%
import networkx as nx

from common import header, load_kg, t, triple_text

# 예시 노드 이름은 현재 언어의 그래프를 따른다 / example nodes follow the active language pack
HUB = t("벤처캐피탈 접근성", "VC accessibility")
FROM, TO = t("저업력 중소기업", "young SMEs"), t("기초연구 선별 지원", "targeted basic-research subsidy")

# %% 1. 작은 그래프로 개념 익히기 ------------------------------------------
header(t("1. 친구 관계 그래프 (무방향)", "1. A friendship graph (undirected)"))
friends = nx.Graph()
names = t("민수 지영 현우 소라 태호", "Alice Bob Carol Dave Eve").split()
friends.add_edges_from([(names[0], names[1]), (names[1], names[2]), (names[2], names[3]), (names[0], names[4])])
print(t("노드:", "Nodes:"), list(friends.nodes))
print(t("엣지:", "Edges:"), list(friends.edges))
print(t(f"{names[1]}의 이웃:", f"Neighbors of {names[1]}:"), list(friends.neighbors(names[1])))
print(t("차수(연결 수):", "Degree:"), dict(friends.degree))
print(t(f"{names[0]} → {names[3]} 최단 경로:", f"Shortest path {names[0]} → {names[3]}:"), nx.shortest_path(friends, names[0], names[3]))

header(t("2. 방향 그래프 + 관계 이름 = 지식그래프(Knowledge Graph)", "2. Directed graph + relation names = knowledge graph"))
kg_toy = nx.MultiDiGraph()
kg_toy.add_edge(t("기초연구", "basic research"), t("특허피인용건수", "patent citations"), type="IMPROVES")
kg_toy.add_edge(t("대기업", "large firms"), t("혁신실적의 질 정체", "stagnant innovation quality"), type="SUFFERS")
for u, v, d in kg_toy.edges(data=True):
    print(f"  ({u}) -[{d['type']}]-> ({v})   ← " + t("트리플(주어, 관계, 목적어)", "a triple (subject, relation, object)"))

# %% 2. 실습 데이터의 지식그래프 불러오기 -----------------------------------
header(t("3. 실습 지식그래프 (data/<언어>/kg.json)", "3. The lab knowledge graph (data/<lang>/kg.json)"))
G = load_kg()
print(t(f"노드 {G.number_of_nodes()}개, 엣지 {G.number_of_edges()}개", f"{G.number_of_nodes()} nodes, {G.number_of_edges()} edges"))
types = {}
for _, d in G.nodes(data=True):
    types[d["type"]] = types.get(d["type"], 0) + 1
print(t("노드 타입 분포:", "Node types:"), types)

print(t(f"\n'{HUB}'에 연결된 관계:", f"\nRelations of '{HUB}':"))
for u, v, d in list(G.out_edges(HUB, data=True)) + list(G.in_edges(HUB, data=True)):
    print("  ", triple_text(u, v, d))

# %% 3. 멀티홉 = 경로 탐색 -------------------------------------------------
header(t(f"4. 문제 → 처방: '{FROM}'에서 '{TO}'까지 (멀티홉)", f"4. Problem → prescription: from '{FROM}' to '{TO}' (multi-hop)"))
U = G.to_undirected()
for path in sorted(nx.all_shortest_paths(U, FROM, TO)):
    print("  " + " → ".join(path))
print(t("  ⇒ 여러 장(2장 문제 진단, 3장 실증, 4장 정책)에 흩어진 사실이 그래프에서는 '한 줄의 경로'가 된다.",
        "  ⇒ Facts scattered across chapters (diagnosis, evidence, policy) become a single path in the graph."))

# %% 4. 중심성 ------------------------------------------------------------
header(t("5. PageRank: 그래프 전체에서 중요한 노드", "5. PageRank: globally important nodes"))
pr = nx.pagerank(nx.Graph(U))
for n, s in sorted(pr.items(), key=lambda x: -x[1])[:5]:
    print(f"  {s:.3f}  {n}")

header(t(f"6. Personalized PageRank: '{FROM}' 관점에서 중요한 노드 (HippoRAG 방식)",
         f"6. Personalized PageRank: important nodes from '{FROM}' (HippoRAG style)"))
ppr = nx.pagerank(nx.Graph(U), personalization={n: (1 if n == FROM else 0) for n in U})
for n, s in sorted(ppr.items(), key=lambda x: -x[1])[:6]:
    print(f"  {s:.3f}  {n}")

# %% 5. 커뮤니티 ----------------------------------------------------------
header(t("7. 커뮤니티 탐지 (Louvain) — MS GraphRAG 는 Leiden 을 사용", "7. Community detection (Louvain) — MS GraphRAG uses Leiden"))
communities = nx.community.louvain_communities(nx.Graph(U), seed=42)
for i, c in enumerate(communities):
    print(t(f"  커뮤니티 {i}: ", f"  community {i}: ") + str(sorted(c)))
print(t("\n  ⇒ 각 커뮤니티를 LLM 으로 요약해 두면 '전체 요약' 질문에 답할 수 있다 (실습 05).",
        "\n  ⇒ Summarizing each community with an LLM lets us answer 'big picture' questions (lab 05)."))
