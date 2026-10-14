# %% [markdown]
# # 실습 09. 시간 인식 지식그래프 (Temporal KG) — 에이전트 메모리 트렌드
# Graphiti(Zep) 같은 도구의 핵심 아이디어를 순수 파이썬으로 흉내 낸다 (구현: temporal_kg.py).
#  - 모든 사실(엣지)에 valid_from / valid_to 를 둔다
#  - 모순되는 새 사실이 오면 옛 엣지를 '삭제'하지 않고 '무효화'한다 (이력 보존)
#  - 질의 시점(as_of)에 따라 다른 답을 돌려준다
# LLM 없이 실행된다. (실제 도구는 LLM 이 '모순 여부'를 판정한다)

# %%
from common import header
from temporal_kg import Fact, demo_kg

header("에피소드가 들어올 때마다 그래프가 갱신된다")
kg = demo_kg()
for f in kg.facts:
    print(f"  ➕ {f.source} = {f.target} (from {f.valid_from}, {f.episode})")
for new in [Fact("한국 R&D 지출(GDP 대비)", "VALUE", "5.2%", "2022-01-01", episode="doc03 (2022년 통계)"),
            Fact("기업 기초연구 지출비중", "VALUE", "11%", "2021-01-01", episode="doc01 (2021년)"),
            Fact("중소기업 평균 업력", "VALUE", "12.5세", "2020-01-01", episode="doc09 (2020년)")]:
    for old in kg.add(new):
        print(f"  ⚠️  무효화: {old.source} = {old.target} (~ {old.valid_to})")
    print(f"  ➕ {new.source} = {new.target} (from {new.valid_from})")

header("같은 질문, 다른 시점")
for date in ("2005-06-30", "2015-06-30", "2023-06-30"):
    print(f"  {date} 기준 R&D 지출 → {kg.query('한국 R&D 지출(GDP 대비)', 'VALUE', date)}, "
          f"기초연구 비중 → {kg.query('기업 기초연구 지출비중', 'VALUE', date)}")

header("이력은 그대로 남아 있다")
for f in kg.facts:
    print(f"  {f.source} -[{f.relation}]-> {f.target}  [{f.valid_from} ~ {f.valid_to or '현재'}]  ← {f.episode}")

print("\n생각해 볼 점: 일반 벡터 DB 에서 'R&D 지출 비중'을 검색하면 2.3%, 3.6%, 5.2% 가 적힌 청크가 모두 나온다.")
print("시간 인식 그래프는 '언제 기준의 사실인가'를 구조로 표현해 어느 값이 유효한지 판단한다.")
