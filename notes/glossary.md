# 용어집

| 용어 | 설명 |
|---|---|
| **Knowledge Graph (KG)** | 엔티티(노드)와 관계(엣지)로 지식을 표현한 그래프 |
| **Triple** | `(주어, 관계, 목적어)` 형태의 사실 단위 |
| **Entity Resolution** | 이름이 달라도 같은 개체를 하나로 병합하는 작업 |
| **Community Detection** | 밀접하게 연결된 노드 그룹을 찾는 작업 (Leiden, Louvain) |
| **Leiden** | Louvain을 개선한 커뮤니티 탐지 알고리즘. MS GraphRAG가 사용 |
| **Community Report / Summary** | 커뮤니티별로 LLM이 생성한 요약 |
| **Local Search** | 엔티티 중심으로 이웃 정보를 모으는 검색 |
| **Global Search** | 커뮤니티 요약들에 map-reduce를 돌려 전역 질문에 답하는 검색 |
| **DRIFT Search** | Global로 방향을 잡고 Local로 파고드는 하이브리드 검색 |
| **Personalized PageRank (PPR)** | 특정 시작 노드 기준으로 중요도를 전파하는 알고리즘. HippoRAG가 사용 |
| **Multi-hop QA** | 여러 사실을 연결해야 답할 수 있는 질의응답 |
| **Text2Cypher** | 자연어를 Neo4j Cypher 쿼리로 변환하는 기법 |
| **PCST** | Prize-Collecting Steiner Tree. G-Retriever의 서브그래프 선택 기법 |
| **Hyperedge** | 셋 이상의 노드를 동시에 잇는 엣지 |
| **Temporal KG** | 사실에 시간 정보(유효 기간)가 붙은 지식그래프 |
| **Bi-temporal** | 사건 발생 시점과 시스템 기록 시점을 모두 관리하는 모델 |
| **Agentic RAG** | LLM 에이전트가 도구를 골라 반복적으로 검색하는 RAG |
| **MCP** | Model Context Protocol. LLM에 도구와 데이터 소스를 연결하는 표준 프로토콜 |
| **Context Engineering** | LLM 컨텍스트에 넣을 정보의 선택, 구조, 순서를 설계하는 일 |
