# 05. 상황별 선택 가이드

## 결정 흐름

```
질문 대부분이 단순 사실 검색인가?
 ├─ 예 → 벡터 RAG + 리랭커 (GraphRAG 불필요)
 └─ 아니오
     ├─ 코퍼스 전체의 요약·테마 질문이 많은가? → MS GraphRAG Global / LazyGraphRAG / RAPTOR
     ├─ 여러 사실을 잇는 멀티홉 질문이 많은가? → HippoRAG 2 / LightRAG / 하이브리드 그래프 확장
     ├─ 도메인 스키마가 명확한가? → 온톨로지 KG + Text2Cypher / KAG
     └─ 대화·에이전트의 장기 기억이 필요한가? → Graphiti(Zep) / Mem0 / Cognee
```

## 상황별 추천

| 상황 | 추천 |
|---|---|
| 단순 FAQ, 사실 검색 | 일반 벡터 RAG + 리랭커 |
| 멀티홉 추론이 잦음 | HippoRAG 2, LightRAG, 그래프 확장 하이브리드 |
| "전체 요약/테마" 질문 | Microsoft GraphRAG Global, LazyGraphRAG, RAPTOR |
| 데이터가 자주 바뀜 | LightRAG(증분), Graphiti(시간 인식) |
| 에이전트 장기 기억 | Graphiti/Zep, Mem0, Cognee |
| 정형 도메인(금융·의료·제조) | 온톨로지 기반 KG + Text2Cypher, KAG |
| 예산이 적음 | LazyGraphRAG, 경량 NLP 추출, SLM 추출기 |

## 도입 체크리스트

- [ ] 벡터 RAG 베이스라인을 먼저 만들고 **실패 사례를 분류**했는가? (멀티홉 실패인지, 전역 질문 실패인지)
- [ ] 평가셋에 멀티홉 질문과 전역 질문이 충분히 포함되어 있는가?
- [ ] 인덱싱 비용(LLM 토큰)을 추정했는가?
- [ ] 엔티티 해소 전략이 있는가?
- [ ] 문서 업데이트 주기에 맞는 증분 전략이 있는가?
- [ ] 답변의 근거(원문 청크)를 추적할 수 있는가?
