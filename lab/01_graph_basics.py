# %% [markdown]
# # 실습 01. 그래프 기초 (networkx)
# - 노드(Node)와 엣지(Edge), 방향/무방향, 이웃, 차수(degree)
# - 경로 탐색(BFS, 최단 경로) = 멀티홉 추론의 기본 연산
# - 중심성(PageRank)과 Personalized PageRank = HippoRAG 의 핵심 도구
# - 커뮤니티 탐지(Louvain) = Microsoft GraphRAG 의 Global Search 재료
# LLM/API 키 없이 실행된다.

# %%
import networkx as nx

from common import header, load_kg, triple_text

# %% 1. 작은 그래프로 개념 익히기 ------------------------------------------
header("1. 친구 관계 그래프 (무방향)")
friends = nx.Graph()
friends.add_edges_from([("민수", "지영"), ("지영", "현우"), ("현우", "소라"), ("민수", "태호")])
print("노드:", list(friends.nodes))
print("엣지:", list(friends.edges))
print("지영의 이웃:", list(friends.neighbors("지영")))
print("차수(연결 수):", dict(friends.degree))
print("민수 → 소라 최단 경로:", nx.shortest_path(friends, "민수", "소라"))

header("2. 방향 그래프 + 관계 이름 = 지식그래프(Knowledge Graph)")
kg_toy = nx.MultiDiGraph()
kg_toy.add_edge("기초연구", "특허피인용건수", type="IMPROVES")
kg_toy.add_edge("대기업", "혁신실적의 질 정체", type="SUFFERS")
for u, v, d in kg_toy.edges(data=True):
    print(f"  ({u}) -[{d['type']}]-> ({v})   ← 트리플(주어, 관계, 목적어)")

# %% 2. 실습 데이터의 지식그래프 불러오기 -----------------------------------
header("3. 실습 지식그래프 (data/kg.json)")
G = load_kg()
print(f"노드 {G.number_of_nodes()}개, 엣지 {G.number_of_edges()}개")
types = {}
for _, d in G.nodes(data=True):
    types[d["type"]] = types.get(d["type"], 0) + 1
print("노드 타입 분포:", types)

print("\n'벤처캐피탈 접근성'에 연결된 관계:")
for u, v, d in list(G.out_edges("벤처캐피탈 접근성", data=True)) + list(G.in_edges("벤처캐피탈 접근성", data=True)):
    print("  ", triple_text(u, v, d))

# %% 3. 멀티홉 = 경로 탐색 -------------------------------------------------
header("4. 문제 → 처방: '저업력 중소기업'에서 '기초연구 선별 지원'까지 (멀티홉)")
U = G.to_undirected()
for path in nx.all_shortest_paths(U, "저업력 중소기업", "기초연구 선별 지원"):
    print("  " + " → ".join(path))
print("  ⇒ 여러 장(2장 문제 진단, 3장 실증, 4장 정책)에 흩어진 사실이 그래프에서는 '한 줄의 경로'가 된다.")

# %% 4. 중심성 ------------------------------------------------------------
header("5. PageRank: 그래프 전체에서 중요한 노드")
pr = nx.pagerank(nx.Graph(U))
for n, s in sorted(pr.items(), key=lambda x: -x[1])[:5]:
    print(f"  {s:.3f}  {n}")

header("6. Personalized PageRank: '저업력 중소기업' 관점에서 중요한 노드 (HippoRAG 방식)")
ppr = nx.pagerank(nx.Graph(U), personalization={n: (1 if n == "저업력 중소기업" else 0) for n in U})
for n, s in sorted(ppr.items(), key=lambda x: -x[1])[:6]:
    print(f"  {s:.3f}  {n}")

# %% 5. 커뮤니티 ----------------------------------------------------------
header("7. 커뮤니티 탐지 (Louvain) — MS GraphRAG 는 Leiden 을 사용")
communities = nx.community.louvain_communities(nx.Graph(U), seed=42)
for i, c in enumerate(communities):
    print(f"  커뮤니티 {i}: {sorted(c)}")
print("\n  ⇒ 각 커뮤니티를 LLM 으로 요약해 두면 '전체 요약' 질문에 답할 수 있다 (실습 05).")
