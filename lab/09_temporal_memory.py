# %% [markdown]
# # 실습 09. 시간 인식 지식그래프 (Temporal KG) — 에이전트 메모리 트렌드
# # Lab 09. Temporal knowledge graph — memory for agents
# Graphiti(Zep) 같은 도구의 핵심 아이디어를 순수 파이썬으로 흉내 낸다 (구현: temporal_kg.py).
#  - 모든 사실(엣지)에 valid_from / valid_to 를 둔다
#  - 모순되는 새 사실이 오면 옛 엣지를 '삭제'하지 않고 '무효화'한다 (이력 보존)
#  - 질의 시점(as_of)에 따라 다른 답을 돌려준다
# LLM 없이 실행된다. / Runs without an LLM.

# %%
from common import get_lang, header, t
from temporal_kg import DEMO, UPDATES, Fact, demo_kg

header(t("에피소드가 들어올 때마다 그래프가 갱신된다", "The graph updates as each episode arrives"))
kg = demo_kg()
for f in kg.facts:
    print(f"  ➕ {f.source} = {f.target} (from {f.valid_from}, {f.episode})")
for src, val, date, ep in UPDATES[get_lang()]:
    new = Fact(src, "VALUE", val, date, episode=ep)
    for old in kg.add(new):
        print(t("  ⚠️  무효화: ", "  ⚠️  invalidated: ") + f"{old.source} = {old.target} (~ {old.valid_to})")
    print(f"  ➕ {new.source} = {new.target} (from {new.valid_from})")

rd, basic = DEMO[get_lang()][0][0], DEMO[get_lang()][2][0]
header(t("같은 질문, 다른 시점", "Same question, different points in time"))
for date in ("2005-06-30", "2015-06-30", "2023-06-30"):
    print(f"  {date}: {rd} → {kg.query(rd, 'VALUE', date)}, {basic} → {kg.query(basic, 'VALUE', date)}")

header(t("이력은 그대로 남아 있다", "History is kept"))
for f in kg.facts:
    print(f"  {f.source} -[{f.relation}]-> {f.target}  [{f.valid_from} ~ {f.valid_to or t('현재', 'now')}]  ← {f.episode}")

print(t("\n생각해 볼 점: 일반 벡터 DB 에서 'R&D 지출 비중'을 검색하면 2.3%, 3.6%, 5.2% 가 적힌 청크가 모두 나온다.\n"
        "시간 인식 그래프는 '언제 기준의 사실인가'를 구조로 표현해 어느 값이 유효한지 판단한다.",
        "\nThink: searching a plain vector DB for 'R&D share of GDP' returns chunks with 2.3%, 3.6% and 5.2% alike.\n"
        "A temporal graph encodes *when* a fact holds, so it can tell which value is valid."))
