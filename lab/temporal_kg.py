"""시간 인식 지식그래프 (실습 09, 라이브 실험실 공용). Graphiti(Zep)의 핵심 아이디어를 단순화한 것."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Fact:
    source: str
    relation: str
    target: str
    valid_from: str
    valid_to: str | None = None  # None = 현재도 유효
    episode: str = ""           # 이 사실을 알게 된 원본 사건(대화/문서)


@dataclass
class TemporalKG:
    facts: list[Fact] = field(default_factory=list)
    # 한 주어가 동시에 하나만 가질 수 있는 관계 (새 값이 오면 옛 값을 무효화)
    exclusive: set[str] = field(default_factory=lambda: {"VALUE"})

    def add(self, fact: Fact) -> list[Fact]:
        """사실을 추가하고, 그 때문에 무효화된 옛 사실 목록을 돌려준다."""
        invalidated = []
        if fact.relation in self.exclusive:
            for old in self.facts:
                if (old.source, old.relation) == (fact.source, fact.relation) and old.valid_to is None \
                        and old.target != fact.target:
                    old.valid_to = fact.valid_from
                    invalidated.append(old)
        self.facts.append(fact)
        return invalidated

    def query(self, source: str, relation: str, as_of: str) -> list[str]:
        return [f.target for f in self.facts
                if f.source == source and f.relation == relation
                and f.valid_from <= as_of and (f.valid_to is None or as_of < f.valid_to)]

    def as_dicts(self) -> list[dict]:
        return [asdict(f) for f in self.facts]


DEMO = {
    "ko": [("한국 R&D 지출(GDP 대비)", "2.3%", "2001-01-01", "doc03 (2001년 통계)"),
           ("한국 R&D 지출(GDP 대비)", "3.6%", "2011-01-01", "doc03 (2011년 통계)"),
           ("기업 기초연구 지출비중", "14%", "2010-01-01", "doc01 (2010년)"),
           ("중소기업 평균 업력", "1.6세", "2001-01-01", "doc09 (2001년)")],
    "en": [("Korea R&D spending (% of GDP)", "2.3%", "2001-01-01", "doc03 (2001 data)"),
           ("Korea R&D spending (% of GDP)", "3.6%", "2011-01-01", "doc03 (2011 data)"),
           ("Basic research share of business R&D", "14%", "2010-01-01", "doc01 (2010)"),
           ("Average age of SMEs", "1.6 years", "2001-01-01", "doc09 (2001)")],
}
# 실습 09 와 화면의 '새 사실 추가' 예시
UPDATES = {
    "ko": [("한국 R&D 지출(GDP 대비)", "5.2%", "2022-01-01", "doc03 (2022년 통계)"),
           ("기업 기초연구 지출비중", "11%", "2021-01-01", "doc01 (2021년)"),
           ("중소기업 평균 업력", "12.5세", "2020-01-01", "doc09 (2020년)")],
    "en": [("Korea R&D spending (% of GDP)", "5.2%", "2022-01-01", "doc03 (2022 data)"),
           ("Basic research share of business R&D", "11%", "2021-01-01", "doc01 (2021)"),
           ("Average age of SMEs", "12.5 years", "2020-01-01", "doc09 (2020)")],
}


def demo_kg(lang: str | None = None) -> TemporalKG:
    """보고서에 나온 '시점별 수치'로 만든 예시 기억. 같은 지표의 새 값이 오면 옛 값이 무효화된다."""
    from common import get_lang
    kg = TemporalKG()
    for src, val, date, ep in DEMO[lang or get_lang()]:
        kg.add(Fact(src, "VALUE", val, date, episode=ep))
    return kg
