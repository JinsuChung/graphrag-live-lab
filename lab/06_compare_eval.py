# %% [markdown]
# # 실습 06. 벡터 vs 그래프 vs 하이브리드 — 검색 성능 비교  /  Lab 06. Retrieval comparison
# 지표: Recall@k = 필요한 사실(근거 그룹) 중 검색된 문서로 뒷받침되는 비율
#       같은 수치가 핵심 요약과 본문에 반복되므로, 사실마다 '인정되는 문서 그룹'을 둔다 (questions.json 의 evidence)
# LLM 없이도 '검색 단계'의 차이를 정량적으로 볼 수 있다.
# 결과는 data/eval_results.json 으로도 저장된다 (발표 페이지에서 사용).

# %%
import json
import os

from common import data_dir, evidence_recall, get_lang, header, load_questions, t
from retrievers import graph_retrieve, hybrid_retrieve, vector_retrieve

METHODS = {"vector": vector_retrieve, "graph": graph_retrieve, "hybrid": hybrid_retrieve}
questions = [q for q in load_questions() if q["type"] != "global"]


results = {"lang": get_lang(), "embedding": os.getenv("EMBEDDING_MODEL") or "local-ngram", "runs": {}}
for k in (3, 5):
    header(f"Recall@{k}")
    print(f"{'id':4} {t('유형', 'type'):10} " + " ".join(f"{m:>7}" for m in METHODS))
    rows = []
    for q in questions:
        row = {"id": q["id"], "type": q["type"]}
        for name, fn in METHODS.items():
            got = fn(q["question"], k=k)
            row[name] = {"docs": got, "recall": evidence_recall(got, q["evidence"])}
        rows.append(row)
        print(f"{q['id']:4} {q['type']:10} " + " ".join(f"{row[m]['recall']:7.2f}" for m in METHODS))
    avg = {m: sum(r[m]["recall"] for r in rows) / len(rows) for m in METHODS}
    print(f"{t('평균', 'Average'):15} " + " ".join(f"{avg[m]:7.2f}" for m in METHODS))
    results["runs"][str(k)] = {"rows": rows, "avg": avg}

out = data_dir() / f"eval_results_{results['embedding'].replace(':', '_').replace('/', '_')}.json"
out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
print(t("\n저장: ", "\nSaved: ") + out.name)
print(t("\n토론 질문:\n 1) 그래프가 이기는 질문과 지는 질문의 공통점은?\n 2) 하이브리드가 가장 안정적인 이유는?\n"
        " 3) 보고서가 1편이 아니라 100편이라면 결과가 어떻게 달라질까?\n 4) 같은 질문을 영문판(DATA_LANG=en)으로 돌리면 무엇이 달라지나?",
        "\nDiscussion:\n 1) What do the questions where the graph wins (or loses) have in common?\n 2) Why is hybrid the most stable?\n"
        " 3) How would results change with 100 reports instead of one?\n 4) What changes with the Korean edition (DATA_LANG=ko)?"))
