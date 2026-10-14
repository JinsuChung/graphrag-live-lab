# GraphRAG 개념 정리

> 기준 시점: 2026년 중반까지의 동향. 이후 발표된 내용은 빠져 있을 수 있음.

## 목차

| 파일 | 내용 |
|---|---|
| [01-overview.md](01-overview.md) | GraphRAG란 무엇이고 왜 필요한가 |
| [02-core-components.md](02-core-components.md) | 인덱싱과 검색의 핵심 구성 요소 |
| [03-methods.md](03-methods.md) | 대표 방법론 계보 (MS GraphRAG, LightRAG, HippoRAG 등) |
| [04-trends-2025-2026.md](04-trends-2025-2026.md) | 최신 트렌드 |
| [05-selection-guide.md](05-selection-guide.md) | 상황별 선택 가이드 |
| [glossary.md](glossary.md) | 용어집 |
| [references.md](references.md) | 논문과 저장소 링크 |

## 한 줄 요약

GraphRAG는 **"무거운 사전 요약 그래프"**에서 출발해 다음 방향으로 옮겨가는 중이다.

- **저비용** (Lazy, Lite, 증분 인덱싱)
- **에이전트 탐색** (Agentic GraphRAG, MCP)
- **시간 인식 메모리** (Temporal KG)
- **벡터와의 하이브리드**

실무에서는 모든 질문에 그래프를 쓰기보다 **멀티홉 질문, 전역 질문, 기억 관리처럼 그래프가 확실히 이기는 곳에만** 쓰는 쪽으로 정리되고 있다.
