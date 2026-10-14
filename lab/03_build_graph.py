# %% [markdown]
# # 실습 03. LLM 으로 지식그래프 만들기 (Indexing)  /  Lab 03. Building a knowledge graph with an LLM
# 두 가지 방법을 고를 수 있다 (.env 의 EXTRACTOR):
#   - lgt    : 교과서 방식. LangChain LLMGraphTransformer (langchain-experimental)
#   - custom : 직접 구현. Pydantic 스키마 + with_structured_output (extraction.py)
# 그다음
#   ② 엔티티 해소: 이름이 다른 같은 개체를 병합
#   ③ data/<언어>/kg_extracted.json 저장
#   ④ 참조 그래프 data/<언어>/kg.json 과 비교 (노드·관계 재현율, 참조에 없는 관계 예시)
#
# 교과서 설정: ChatOpenAI(model="gpt-4o", temperature=0)
# 이 실습 설정: .env 의 LLM_MODEL + LLM_TEMPERATURE (README 의 모델 선택 안내 참고)

# %%
import json
import os
import time

from common import data_dir, get_llm, header, load_docs, t
from extraction import EXTRACT_PROMPT, Extraction, compare_graphs, lgt_extract, make_extractor, merge

EXTRACTOR = os.getenv("EXTRACTOR", "custom").strip()
# 스키마 기반 추출을 원하면 허용 타입을 준다 (kg.json 과 같은 어휘). 비우면 자유 추출.
SCHEMA_NODES = ["FirmGroup", "Indicator", "Problem", "Policy", "Finance", "ResearchType", "Actor", "Outcome"]

llm = get_llm()
docs = load_docs()
if llm is None:
    header(t("LLM_MODEL 이 설정되지 않았습니다", "LLM_MODEL is not set"))
    print(t("이 실습은 LLM 이 필요합니다. .env 에 LLM_MODEL 과 API 키를 설정하세요.\n"
            "대신 참조 그래프 kg.json 으로 나머지 실습을 진행할 수 있습니다.",
            "This lab needs an LLM. Set LLM_MODEL and an API key in .env.\n"
            "You can still run the other labs with the reference graph kg.json."))
    print(t("\n[custom 방식에서 LLM 에 보내질 프롬프트 예시]", "\n[Example prompt sent to the LLM in custom mode]"))
    print(EXTRACT_PROMPT.format(text=docs[8].page_content[:600] + " …"))
    raise SystemExit(0)

# %% ① 추출 ---------------------------------------------------------------
header(f"{t('추출 방식', 'extractor')}: {EXTRACTOR}  ·  {t('모델', 'model')}: {os.getenv('LLM_MODEL')}  ·  "
       f"temperature: {os.getenv('LLM_TEMPERATURE') or t('(모델 기본값)', '(model default)')}")
t0 = time.perf_counter()
CONCURRENCY = int(os.getenv("EXTRACT_CONCURRENCY", "6"))  # 문서 하나에 30초 안팎 → 여러 개를 동시에 보낸다
if EXTRACTOR == "lgt":
    kg = lgt_extract(llm, docs, allowed_nodes=SCHEMA_NODES if os.getenv("SCHEMA") == "1" else None,
                     concurrency=CONCURRENCY)
else:
    extractor = make_extractor(llm)
    outs = extractor.batch([{"text": d.page_content} for d in docs], config={"max_concurrency": CONCURRENCY})
    results: dict[str, Extraction] = {}
    for doc, ex in zip(docs, outs):
        results[doc.metadata["doc_id"]] = ex
        print(f"  {doc.metadata['doc_id']}: {t('엔티티', 'entities')} {len(ex.entities)}, {t('관계', 'relations')} {len(ex.relations)}")
    kg = merge(results)
print(t(f"소요 시간 {time.perf_counter() - t0:.0f}초", f"elapsed {time.perf_counter() - t0:.0f}s"))

# %% ② 저장 ---------------------------------------------------------------
dropped = kg.pop("dropped")
out = data_dir() / "kg_extracted.json"
out.write_text(json.dumps(kg, ensure_ascii=False, indent=1), encoding="utf-8")
header(t("결과", "Result"))
print(t(f"노드 {len(kg['nodes'])}개, 관계 {len(kg['edges'])}개 → {out.name}", f"{len(kg['nodes'])} nodes, {len(kg['edges'])} relations → {out.name}"))
print(t(f"엔티티 목록에 없는 이름을 가리켜 버린 관계 {len(dropped)}개:", f"{len(dropped)} relations dropped (pointing to unknown entities):"), dropped[:5])

# %% ③ 참조 그래프와 비교 -------------------------------------------
ref = json.loads((data_dir() / "kg.json").read_text(encoding="utf-8"))
c = compare_graphs(kg, ref)
header(t("LLM 그래프 vs 참조 그래프 (kg.json)", "LLM graph vs reference graph (kg.json)"))
print(t(f"  참조 노드 재현율 {c['node_recall']:.0%}   참조 관계 재현율 {c['edge_recall']:.0%}",
        f"  reference node recall {c['node_recall']:.0%}   reference relation recall {c['edge_recall']:.0%}"))
print(t(f"  LLM 관계 중 참조에도 있는 비율 {c['edge_in_ref_ratio']:.0%}   서로 다른 관계 이름 {c['relation_types']}종",
        f"  share of LLM relations also in reference {c['edge_in_ref_ratio']:.0%}   distinct relation names {c['relation_types']}"))
print(t("\n  [참조에는 있는데 LLM 이 놓친 관계]", "\n  [In the reference but missed by the LLM]"))
for x in c["missed_examples"]:
    print("   -", x)
print(t("\n  [LLM 이 만들었지만 참조에는 없는 관계 — 틀린 것인지, 참조가 빠뜨린 것인지 원문으로 확인]",
        "\n  [Made by the LLM but not in the reference — check the source: wrong, or missing from the reference?]"))
for x in c["extra_examples"]:
    print("   +", x)
print(t("\n토론: 같은 설정으로 한 번 더 돌리면 결과가 똑같은가? temperature 0 이면 충분한가?\n"
        "      '~일 가능성이 있다' 같은 유보 표현이 관계로 바뀌면서 확정된 사실처럼 보이지 않는가?\n"
        "\n그래프를 바꿔 실험하려면 .env 에 KG_FILE=kg_extracted.json 을 넣고 서버/실습을 다시 실행하세요.",
        "\nDiscuss: does a second run with the same settings give the same graph? Is temperature 0 enough?\n"
        "         Do hedged claims ('may be due to') turn into relations that look like settled facts?\n"
        "\nTo experiment with this graph, set KG_FILE=kg_extracted.json in .env and rerun the server/labs."))
