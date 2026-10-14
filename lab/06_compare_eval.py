# %% [markdown]
# # 실습 06. 벡터 vs 그래프 vs 하이브리드 — 검색 성능 비교
# 지표: Recall@k = 필요한 사실(근거 그룹) 중 검색된 문서로 뒷받침되는 비율
#       같은 수치가 핵심 요약과 본문에 반복되므로, 사실마다 '인정되는 문서 그룹'을 둔다 (questions.json 의 evidence)
# LLM 없이도 '검색 단계'의 차이를 정량적으로 볼 수 있다.
# 결과는 data/eval_results.json 으로도 저장된다 (발표 페이지에서 사용).

# %%
import json
import os

from common import DATA, evidence_recall, header, load_questions
from retrievers import graph_retrieve, hybrid_retrieve, vector_retrieve

METHODS = {"vector": vector_retrieve, "graph": graph_retrieve, "hybrid": hybrid_retrieve}
questions = [q for q in load_questions() if q["type"] != "global"]


results = {"embedding": os.getenv("EMBEDDING_MODEL") or "local-ngram", "runs": {}}
for k in (3, 5):
    header(f"Recall@{k}")
    print(f"{'id':4} {'유형':10} " + " ".join(f"{m:>7}" for m in METHODS))
    rows = []
    for q in questions:
        row = {"id": q["id"], "type": q["type"]}
        for name, fn in METHODS.items():
            got = fn(q["question"], k=k)
            row[name] = {"docs": got, "recall": evidence_recall(got, q["evidence"])}
        rows.append(row)
        print(f"{q['id']:4} {q['type']:10} " + " ".join(f"{row[m]['recall']:7.2f}" for m in METHODS))
    avg = {m: sum(r[m]["recall"] for r in rows) / len(rows) for m in METHODS}
    print(f"{'평균':15} " + " ".join(f"{avg[m]:7.2f}" for m in METHODS))
    results["runs"][str(k)] = {"rows": rows, "avg": avg}

out = DATA / f"eval_results_{results['embedding'].replace(':', '_').replace('/', '_')}.json"
out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"\n저장: {out.name}")
print("\n토론 질문:")
print(" 1) 그래프가 이기는 질문과 지는 질문의 공통점은?")
print(" 2) 하이브리드가 가장 안정적인 이유는?")
print(" 3) 보고서가 1편이 아니라 100편이라면 결과가 어떻게 달라질까?")
