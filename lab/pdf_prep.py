"""PDF 전처리: 로드 → 정제 → 섹션(주제별 문서) 분할.

실습 00(스크립트)과 라이브 실험실의 '문서 처리' 모드가 함께 쓴다.
PDF 에서 뽑은 텍스트에는 차트 눈금 숫자, 각주, 머리글 같은 잡음이 섞여 있다.
이를 규칙 기반으로 걸러 내고, 무엇을 왜 지웠는지도 함께 기록한다.
"""
from __future__ import annotations

import re
from pathlib import Path

from common import DATA

PDF_PATH = DATA / "source" / "bok_2024_05_innovation_growth.pdf"
# 보고서는 저작권이 한국은행에 있어 저장소에 넣지 않는다. 공식 게시물의 첨부파일 링크에서 직접 받는다.
#   게시물: https://www.bok.or.kr/portal/bbs/P0002359/view.do?nttId=10084275&menuNo=200066
PDF_URL = ("https://www.bok.or.kr/fileSrc/portal/a3c69d37686c908e5bce981115a9969e/19/"
           "e4ea642765de4230ad6a650636f23c6e.pdf")
REPORT_PAGE = "https://www.bok.or.kr/portal/bbs/P0002359/view.do?nttId=10084275&menuNo=200066"
PAGE_OFFSET = 61  # PDF 1쪽 = 보고서 61쪽 (경제전망보고서 III장)
SOURCE = "한국은행, 경제전망보고서(2024.5) III. 중장기 심층연구 「혁신과 경제성장 – 우리나라 기업의 혁신활동 분석 및 평가」"

HEADERS = {"III. 중장기 심층연구", "혁신과 경제성장 – 우리나라 기업의 혁신활동 분석 및 평가"}
CHAPTERS = {  # 장 제목 (문단 번호와 헷갈리지 않도록 따로 처리)
    "1. 검토배경", "2. 우리나라 기업의 혁신활동 현황과 특징", "3. 기업혁신활동 구성요소에 대한 실증분석 및 평가",
    "4. 혁신정책의 경제적 효과에 관한 시나리오 분석", "5. 결론 및 시사점",
}

# 문단 번호 범위 → 주제별 문서 (보고서 목차를 따라 사람이 정한 경계)
SECTIONS = [
    ("doc01", "핵심 요약 (KEY TAKEAWAYS)", "takeaways", None),
    ("doc02", "검토배경: 인구 감소와 성장잠재력, 혁신의 의미", "para", (1, 2)),
    ("doc03", "우리나라 혁신활동 지표: R&D 지출과 특허", "para", (3, 4)),
    ("doc04", "생산성 둔화와 분석의 구성", "para", (5, 8)),
    ("doc05", "기업 혁신활동의 단계와 구성요소", "para", (9, 9)),
    ("doc06", "혁신기업의 정의와 생산성 둔화", "para", (10, 11)),
    ("doc07", "혁신기업의 분류: 대기업·고업력·저업력 중소기업", "para", (12, 14)),
    ("doc08", "대기업: 혁신실적의 양은 늘었지만 질은 정체", "para", (15, 16)),
    ("doc09", "저업력 중소기업: 자금조달 어려움과 신생기업 진입 감소", "para", (17, 19)),
    ("doc10", "문제의 원인 ①: 기초연구 지출비중 축소", "para", (20, 21)),
    ("doc11", "문제의 원인 ②③: 벤처캐피탈 기능 부족과 혁신창업가 부족", "para", (22, 24)),
    ("doc12", "실증분석: 기초연구·응용연구와 혁신실적의 양과 질", "para", (25, 28)),
    ("doc13", "실증분석: 벤처캐피탈 접근성과 투자회수시장", "para", (29, 33)),
    ("doc14", "실증분석: 민간·정부 벤처캐피탈과 펀드 유형 (BOX 1 포함)", "para+box1", (34, 35)),
    ("doc15", "실증분석: 「똑똑한 이단아」의 진로 선택", "para", (36, 42)),
    ("doc16", "시나리오 분석: 기초연구 강화 정책의 효과", "para", (43, 50)),
    ("doc17", "시나리오 분석: 혁신신생기업 육성 정책의 효과", "para", (51, 52)),
    ("doc18", "결론 및 정책 시사점", "para", (53, 56)),
    ("doc19", "BOX 2: 여성의 STEM 전공 선호 결정요인", "box2", None),
]

FOOTNOTE = re.compile(r"^\d{1,2}\) ")          # 줄 맨 앞(들여쓰기 없음)의 '12) ' → 페이지 하단 각주 시작
PARA = re.compile(r"^(\d{1,2})\. ")             # '23. ' 문단 번호
CHART_START = re.compile(r"^\s*(\[그림|\[표|<|주:|자료:)")


def hangul(s: str) -> int:
    return len(re.findall(r"[가-힣]", s))


def load_pages(path: Path = PDF_PATH) -> list[str]:
    """LangChain PyPDFLoader 로 페이지별 텍스트를 읽는다."""
    from langchain_community.document_loaders import PyPDFLoader
    return [d.page_content for d in PyPDFLoader(str(path)).load()]


def annotate_page(text: str) -> list[dict]:
    """페이지의 모든 줄에 대해 {line, reason} 을 순서대로 돌려준다. reason 이 None 이면 남기는 줄."""
    raw = text.split("\n")
    out = []
    in_footnote = False
    for i, line in enumerate(raw):
        s = line.strip()
        nxt = raw[i + 1].strip() if i + 1 < len(raw) else ""
        reason = None
        if in_footnote:
            reason = "각주"
        elif FOOTNOTE.match(line):
            in_footnote, reason = True, "각주"
        elif s.startswith(("KEY TAKEAWAYS", "BOX ", "별첨")):
            reason = None  # 구조 표지는 남긴다
        elif not s:
            reason = "빈 줄"
        elif s in HEADERS or s.isdigit():
            reason = "머리글·쪽번호"
        elif CHART_START.match(line):
            reason = "차트·표 캡션/주석"
        elif nxt.startswith(("[그림", "[표")):
            reason = "차트 제목"
        elif hangul(s) < 8 and not re.search(r"(다|음|함)\.\)?$|\)\.$", s):
            reason = "차트 숫자·축 라벨"
        out.append({"line": line.lstrip(), "reason": reason})  # 줄 끝 공백은 살린다 (단어 경계 정보)
    return out


def clean_page(text: str) -> tuple[list[str], list[dict]]:
    """한 페이지를 정제한다. (남긴 줄, 지운 줄과 이유) 를 돌려준다."""
    ann = annotate_page(text)
    kept = [a["line"] for a in ann if a["reason"] is None]
    removed = [{"line": a["line"].strip(), "reason": a["reason"]} for a in ann if a["reason"]]
    return kept, removed


def split_sections(pages: list[str]) -> list[dict]:
    """정제된 페이지들을 문단 번호 기준으로 모은 뒤 SECTIONS 경계대로 문서를 만든다."""
    paras: dict[int, dict] = {}       # 문단 번호 → {text, pages}
    takeaways, box1, box2 = [], [], []
    expected, mode = 1, "front"
    for pno, page in enumerate(pages):
        kept, _ = clean_page(page)
        for raw_line in kept:
            line = raw_line.strip()
            if line.startswith("KEY TAKEAWAYS"):
                mode = "takeaways"; continue
            if line.startswith("BOX 1"):
                mode = "box1"
            elif line.startswith("BOX 2"):
                mode = "box2"
            elif line.startswith("별첨"):
                mode = "appendix"
            if line in CHAPTERS:
                continue
            m = PARA.match(line)
            if mode in ("front", "takeaways", "para") and m and int(m.group(1)) == expected:
                mode, cur = "para", expected
                paras[cur] = {"text": raw_line, "pages": {pno}}
                expected += 1
                continue
            if mode == "takeaways":
                takeaways.append(raw_line)
            elif mode == "para":
                paras[cur]["text"] += raw_line
                paras[cur]["pages"].add(pno)
            elif mode == "box1":
                box1.append(raw_line)
            elif mode == "box2":
                box2.append(raw_line)

    def page_range(ps: set[int]) -> str:
        return f"{PAGE_OFFSET + min(ps)}–{PAGE_OFFSET + max(ps)}쪽"

    docs = []
    for doc_id, title, kind, rng in SECTIONS:
        if kind == "takeaways":
            body, where = "".join(takeaways), f"KEY TAKEAWAYS, {PAGE_OFFSET + 1}쪽"
        elif kind == "box2":
            body, where = "".join(box2), "BOX 2"
        else:
            nums = range(rng[0], rng[1] + 1)
            parts = [paras[n]["text"] for n in nums if n in paras]
            pages_used = set().union(*(paras[n]["pages"] for n in nums if n in paras))
            where = f"문단 {rng[0]}–{rng[1]}, {page_range(pages_used)}"
            if kind == "para+box1":
                parts.append("\n\n[BOX 1] " + "".join(box1))
                where += " + BOX 1"
            body = "\n\n".join(parts)
        body = re.sub(r"[ \t]+", " ", body).replace("▢", "\n▢").replace("▪", "\n▪").strip()
        docs.append({"doc_id": doc_id, "title": title, "where": where, "text": body})
    return docs


def write_docs(docs: list[dict], out_dir: Path = DATA / "docs") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.md"):
        old.unlink()
    for d in docs:
        slug = re.sub(r"[^0-9A-Za-z가-힣]+", "_", d["title"]).strip("_")[:24]
        (out_dir / f"{d['doc_id']}_{slug}.md").write_text(
            f"# {d['title']}\n\n> 출처: {SOURCE} — {d['where']}\n\n{d['text']}\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# 처음 실행할 때: PDF 내려받기 → 문서 생성
# ---------------------------------------------------------------------------
def download_pdf(path: Path = PDF_PATH) -> Path:
    """한국은행 공식 링크에서 보고서 PDF 를 내려받는다 (이미 있으면 그대로 사용)."""
    if path.exists() and path.stat().st_size > 100_000:
        return path
    import urllib.request
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"보고서 PDF 를 한국은행 홈페이지에서 내려받습니다…\n  {PDF_URL}")
    try:
        req = urllib.request.Request(PDF_URL, headers={"User-Agent": "Mozilla/5.0 (graphrag-live-lab)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        if not data.startswith(b"%PDF"):
            raise ValueError("PDF 가 아닌 응답을 받았습니다")
        path.write_bytes(data)
    except Exception as e:
        raise SystemExit(
            f"PDF 를 자동으로 받지 못했습니다 ({e}).\n"
            f"아래 게시물에서 「III. [중장기 심층연구] 혁신과 경제성장…pdf」를 직접 받아\n"
            f"  {path}\n로 저장한 뒤 다시 실행하세요.\n  {REPORT_PAGE}")
    print(f"  저장: {path} ({path.stat().st_size / 1e6:.1f} MB)")
    return path


def ensure_docs() -> None:
    """data/docs 가 비어 있으면 PDF 를 받아 주제별 문서를 만든다 (실습 00 과 같은 과정)."""
    if any((DATA / "docs").glob("*.md")):
        return
    download_pdf()
    docs = split_sections(load_pages())
    write_docs(docs)
    print(f"  주제별 문서 {len(docs)}개를 data/docs 에 만들었습니다.")
