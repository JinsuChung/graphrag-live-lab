# 03. 대표 방법론 계보

## 요약 표

| 방법 | 출처 | 핵심 아이디어 | 포인트 |
|---|---|---|---|
| **Microsoft GraphRAG** | Microsoft, 2024 | 엔티티 그래프 + 계층 커뮤니티 요약 + Local/Global 검색 | 붐의 시작. 인덱싱 비용이 매우 큼 |
| **RAPTOR** | Stanford, 2024 | 청크를 재귀적으로 클러스터링하고 요약해 트리 구성 | 그래프는 아니지만 계층 요약 계열 |
| **LightRAG** | HKU, 2024 | Low-level(엔티티) + High-level(주제) 이중 검색, 증분 업데이트 | 가볍고 빨라서 오픈소스 인기 1순위 |
| **LazyGraphRAG** | Microsoft, 2024 말 | 사전 요약 없이 질의 시점에만 LLM 처리 | 인덱싱 비용을 벡터 RAG 수준으로 낮춤 |
| **HippoRAG / HippoRAG 2** | OSU, 2024 / 2025 | 해마 기억 이론에서 착안. KG에 Personalized PageRank 적용 | 멀티홉 강함, 지속 학습 메모리 관점 |
| **Think-on-Graph (ToG / ToG-2)** | 2023 / 2024 | LLM이 에이전트처럼 KG 위를 빔서치로 탐색 | LLM과 KG의 긴밀한 결합 추론 |
| **G-Retriever** | 2024 | PCST로 서브그래프를 선택하고 GNN으로 인코딩해 LLM에 전달 | 학습 기반 그래프 검색 |
| **GNN-RAG** | 2024 | GNN으로 KGQA 답 후보와 경로를 찾고 LLM이 추론 | 학습 기반 |
| **KAG** | Ant Group, 2024 | 스키마/온톨로지 기반 지식 구축 + 논리 형식 추론 | 전문 도메인(금융·의료) 지향 |
| **PathRAG** | 2025 | 관계 경로 단위로 검색하고 흐름 기반으로 가지치기 | 컨텍스트 중복 감소 |
| **NodeRAG** | 2025 | 이질적 노드 타입(엔티티, 관계, 요약 등)으로 그래프 설계 | LightRAG 이후 구조 개선 |
| **MiniRAG** | HKU, 2025 | 소형 모델(SLM)에서도 동작하는 경량 구조 | 온디바이스와 저비용 |
| **HyperGraphRAG** | 2025 | n-ary 관계를 하이퍼엣지로 표현 | 트리플의 표현력 한계 보완 |
| **Graphiti (Zep)** | Zep, 2024~2025 | 시간 인식(bi-temporal) 지식그래프, 증분 업데이트 | 에이전트 메모리의 대표 사례 |

## 계보 관점으로 보기

```
[계층 요약형]
  RAPTOR ─┐
          ├─> Microsoft GraphRAG ─> LazyGraphRAG / DRIFT
          │
[경량·증분형]
  LightRAG ─> PathRAG / NodeRAG / MiniRAG
          │
[그래프 알고리즘 기반 기억형]
  HippoRAG ─> HippoRAG 2
          │
[LLM 에이전트 탐색형]
  Think-on-Graph ─> ToG-2 ─> Agentic GraphRAG (도구 호출, MCP)
          │
[학습 기반 GNN형]
  G-Retriever, GNN-RAG
          │
[구조·도메인형]
  KAG, 온톨로지 기반 KG + Text2Cypher
          │
[시간·메모리형]
  Graphiti/Zep, Mem0 graph, Cognee
```

## 두 대표 방식 비교: Microsoft GraphRAG vs LightRAG

| 항목 | Microsoft GraphRAG | LightRAG |
|---|---|---|
| 인덱싱 비용 | 높음 (커뮤니티 요약 생성) | 낮음 (요약 없이 키-값 프로파일) |
| 전역 질문 | 강함 (Global Search) | 중간 (High-level 키워드 검색) |
| 지역 질문 | 좋음 | 좋음 |
| 증분 업데이트 | 제한적 (재계산 필요) | 지원 (그래프 병합) |
| 구현 난이도 | 파이프라인이 복잡함 | 단순함 |
