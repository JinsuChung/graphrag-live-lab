"""PDF 전처리: 내려받기 → 로드 → 정제 → 섹션(주제별 문서) 분할.  (PDF preprocessing)

실습 00(스크립트)과 라이브 실험실의 '문서 처리' 모드가 함께 쓴다.
PDF 에서 뽑은 텍스트에는 차트 눈금 숫자, 각주, 머리글 같은 잡음이 섞여 있다. 이를 걸러 내고,
무엇을 왜 지웠는지도 함께 기록한다. 같은 보고서라도 판본마다 알맞은 정제 방법이 다르다:
  - 국문판(ko): 줄의 한글 글자 수·패턴으로 판단하는 규칙
  - 영문판(en): PDF 의 글꼴 크기로 판단 (본문 11pt, 캡션 10pt, 주석 8.8pt, 각주 9pt …)
두 판본은 문단 번호(1~56)가 1:1 로 대응하므로 같은 경계로 doc01~doc19 를 만든다.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from common import DATA, data_dir, get_lang, t

# 보고서는 저작권이 한국은행에 있어 저장소에 넣지 않는다. 공식 게시물의 첨부파일 링크에서 직접 받는다.
REPORTS = {
    "ko": {
        "pdf": DATA / "source" / "bok_2024_05_innovation_growth.pdf",
        "url": "https://www.bok.or.kr/fileSrc/portal/a3c69d37686c908e5bce981115a9969e/19/"
               "e4ea642765de4230ad6a650636f23c6e.pdf",
        "page": "https://www.bok.or.kr/portal/bbs/P0002359/view.do?nttId=10084275&menuNo=200066",
        "file_label": "III. [중장기 심층연구] 혁신과 경제성장-우리나라 기업의 혁신활동 분석 및 평가.pdf",
        "offset": 61,  # PDF 1쪽 = 보고서 61쪽 (경제전망보고서 III장)
        "source": "한국은행, 경제전망보고서(2024.5) III. 중장기 심층연구 "
                  "「혁신과 경제성장 – 우리나라 기업의 혁신활동 분석 및 평가」",
    },
    "en": {
        "pdf": DATA / "source" / "bok_2024_05_innovation_growth_en.pdf",
        "url": "https://www.bok.or.kr/fileSrc/imerEng/7740405c78f04e46aafc28ad095eed73/1/"
               "19f3675b4ec245ba8c676ddae1ce247c.pdf",
        "page": "https://www.bok.or.kr/imerEng/bbs/B0000519/view.do?nttId=10086298&menuNo=600379",
        "file_label": "[May 2024 In-depth Analysis] Innovation and Economic Growth, Review of Korean Firms' "
                      "Innovation Performance.pdf",
        "offset": 56,  # PDF page 1 = report page 56
        "source": "Bank of Korea, Economic Outlook (May 2024) III. In-depth Analysis, "
                  "\"Innovation and Economic Growth: Review of Korean Firms' Innovation Performance\"",
    },
}


def cfg(lang: str | None = None) -> dict:
    return REPORTS[lang or get_lang()]


def pdf_path(lang: str | None = None) -> Path:
    return cfg(lang)["pdf"]


# 문단 번호 범위 → 주제별 문서 (보고서 목차를 따라 사람이 정한 경계, 두 판본 공통)
SECTIONS = [
    ("doc01", "takeaways", None, "핵심 요약 (KEY TAKEAWAYS)", "Key takeaways"),
    ("doc02", "para", (1, 2), "검토배경: 인구 감소와 성장잠재력, 혁신의 의미",
     "Background: population decline, growth potential and innovation"),
    ("doc03", "para", (3, 4), "우리나라 혁신활동 지표: R&D 지출과 특허", "Korea's innovation indicators: R&D and patents"),
    ("doc04", "para", (5, 8), "생산성 둔화와 분석의 구성", "Productivity slowdown and outline of the analysis"),
    ("doc05", "para", (9, 9), "기업 혁신활동의 단계와 구성요소", "Stages and components of firm innovation"),
    ("doc06", "para", (10, 11), "혁신기업의 정의와 생산성 둔화", "Innovative firms: definition and productivity slowdown"),
    ("doc07", "para", (12, 14), "혁신기업의 분류: 대기업·고업력·저업력 중소기업",
     "Classifying innovative firms: large firms, old SMEs, young SMEs"),
    ("doc08", "para", (15, 16), "대기업: 혁신실적의 양은 늘었지만 질은 정체",
     "Large firms: more patents, stagnant quality"),
    ("doc09", "para", (17, 19), "저업력 중소기업: 자금조달 어려움과 신생기업 진입 감소",
     "Young SMEs: financing difficulties and fewer new entrants"),
    ("doc10", "para", (20, 21), "문제의 원인 ①: 기초연구 지출비중 축소", "Cause 1: shrinking share of basic research"),
    ("doc11", "para", (22, 24), "문제의 원인 ②③: 벤처캐피탈 기능 부족과 혁신창업가 부족",
     "Causes 2-3: weak venture capital and too few innovative entrepreneurs"),
    ("doc12", "para", (25, 28), "실증분석: 기초연구·응용연구와 혁신실적의 양과 질",
     "Evidence: basic vs. applied research and innovation quantity/quality"),
    ("doc13", "para", (29, 33), "실증분석: 벤처캐피탈 접근성과 투자회수시장", "Evidence: VC access and the secondary market"),
    ("doc14", "para+box1", (34, 35), "실증분석: 민간·정부 벤처캐피탈과 펀드 유형 (BOX 1 포함)",
     "Evidence: private vs. government VC and fund types (incl. BOX 1)"),
    ("doc15", "para", (36, 42), "실증분석: 「똑똑한 이단아」의 진로 선택", "Evidence: career choices of \"smart mavericks\""),
    ("doc16", "para", (43, 50), "시나리오 분석: 기초연구 강화 정책의 효과", "Scenarios: strengthening basic research"),
    ("doc17", "para", (51, 52), "시나리오 분석: 혁신신생기업 육성 정책의 효과", "Scenarios: fostering innovative start-ups"),
    ("doc18", "para", (53, 56), "결론 및 정책 시사점", "Conclusion and policy implications"),
    ("doc19", "box2", None, "BOX 2: 여성의 STEM 전공 선호 결정요인", "BOX 2: what drives women's preference for STEM majors"),
]

PARA = re.compile(r"^(\d{1,2})\. ")             # '23. ' 문단 번호
MARKERS = ("KEY TAKEAWAYS", "BOX ", "별첨", "Annex")

# ── 국문판 규칙 ──
KO_HEADERS = {"III. 중장기 심층연구", "혁신과 경제성장 – 우리나라 기업의 혁신활동 분석 및 평가"}
KO_CHAPTERS = {  # 장 제목 (문단 번호와 헷갈리지 않도록 따로 처리)
    "1. 검토배경", "2. 우리나라 기업의 혁신활동 현황과 특징", "3. 기업혁신활동 구성요소에 대한 실증분석 및 평가",
    "4. 혁신정책의 경제적 효과에 관한 시나리오 분석", "5. 결론 및 시사점",
}
FOOTNOTE = re.compile(r"^\d{1,2}\) ")          # 줄 맨 앞(들여쓰기 없음)의 '12) ' → 페이지 하단 각주 시작
CHART_START = re.compile(r"^\s*(\[그림|\[표|<|주:|자료:)")

# ── 영문판 규칙: 글꼴 크기(pt) ──
EN_BODY = (10.85, 11.15)                       # 본문·요약·BOX 본문은 11pt


def hangul(s: str) -> int:
    return len(re.findall(r"[가-힣]", s))


def load_pages(path: Path | None = None) -> list[str]:
    """LangChain PyPDFLoader 로 페이지별 텍스트를 읽는다."""
    from langchain_community.document_loaders import PyPDFLoader
    return [d.page_content for d in PyPDFLoader(str(path or pdf_path())).load()]


# ---------------------------------------------------------------------------
# 정제: 페이지의 모든 줄에 {line, reason} (reason=None 이면 남기는 줄)
# ---------------------------------------------------------------------------
def _annotate_ko(text: str) -> list[dict]:
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
        elif s.startswith(MARKERS):
            reason = None  # 구조 표지는 남긴다
        elif not s:
            reason = "빈 줄"
        elif s in KO_HEADERS or s.isdigit():
            reason = "머리글·쪽번호"
        elif CHART_START.match(line):
            reason = "차트·표 캡션/주석"
        elif nxt.startswith(("[그림", "[표")):
            reason = "차트 제목"
        elif hangul(s) < 8 and not re.search(r"(다|음|함)\.\)?$|\)\.$", s):
            reason = "차트 숫자·축 라벨"
        out.append({"line": line.lstrip(), "reason": reason})  # 줄 끝 공백은 살린다 (단어 경계 정보)
    return out


@lru_cache(maxsize=2)
def _reader(path: str):
    from pypdf import PdfReader
    return PdfReader(path)


def _font_lines(pi: int) -> list[list[tuple[str, float]]]:
    """영문판 한 페이지를 (글자 조각, 글꼴 크기) 의 줄 목록으로 읽는다."""
    lines: list[list[tuple[str, float]]] = [[]]

    def visit(text, cm, tm, font_dict, font_size):
        size = font_size * (tm[0] or 1) * (cm[0] or 1)
        for j, part in enumerate(text.split("\n")):
            if j > 0:
                lines.append([])
            if part:
                lines[-1].append((part, size))

    _reader(str(pdf_path("en"))).pages[pi].extract_text(visitor_text=visit)
    return lines


def _annotate_en(pi: int) -> list[dict]:
    out = []
    for pieces in _font_lines(pi):
        full = "".join(p for p, _ in pieces)
        s = full.strip()
        if not s:
            out.append({"line": "", "reason": t("빈 줄", "blank line")})
            continue
        chars: dict[float, int] = {}
        for p, size in pieces:
            chars[round(size, 1)] = chars.get(round(size, 1), 0) + len(p.strip())
        main = max(chars, key=chars.get)
        if s.startswith(MARKERS):
            out.append({"line": s, "reason": None, "size": main})
            continue
        if EN_BODY[0] <= main <= EN_BODY[1]:
            # 본문 줄: 작은 위첨자(각주 번호 등)는 빼고 본문 크기 조각만 남긴다
            body = "".join(p for p, size in pieces if EN_BODY[0] <= size <= EN_BODY[1])
            out.append({"line": body.lstrip(), "reason": None, "size": main})
            continue
        if main >= 12:
            reason = t("제목 (큰 글꼴)", "heading (large font)")
        elif main >= 9.9:
            reason = t("차트·표 제목/캡션 (10pt)", "chart/table caption (10pt)")
        elif main >= 8.7:
            reason = t("주석·출처·각주 (9pt 안팎)", "notes/sources/footnotes (~9pt)")
        else:
            reason = t("머리글·쪽번호·차트 숫자 (작은 글꼴)", "header/page no./chart labels (small font)")
        out.append({"line": s, "reason": f"{reason} · {main:g}pt", "size": main})
    return out


def annotate(pi: int, pages: list[str]) -> list[dict]:
    """현재 언어의 정제 규칙으로 pi 번째 페이지의 모든 줄을 판정한다."""
    return _annotate_en(pi) if get_lang() == "en" else _annotate_ko(pages[pi])


def clean(pi: int, pages: list[str]) -> tuple[list[str], list[dict]]:
    """(남긴 줄, 지운 줄과 이유)."""
    ann = annotate(pi, pages)
    kept = [a["line"] for a in ann if a["reason"] is None]
    removed = [{"line": a["line"].strip(), "reason": a["reason"]} for a in ann if a["reason"]]
    return kept, removed


# ---------------------------------------------------------------------------
# 섹션 분할
# ---------------------------------------------------------------------------
def split_sections(pages: list[str]) -> list[dict]:
    """정제된 페이지들을 문단 번호 기준으로 모은 뒤 SECTIONS 경계대로 문서를 만든다."""
    en = get_lang() == "en"
    paras: dict[int, dict] = {}       # 문단 번호 → {text, pages}
    takeaways, box1, box2 = [], [], []
    expected, mode, cur = 1, "front", None
    for pno in range(len(pages)):
        kept, _ = clean(pno, pages)
        for raw_line in kept:
            line = raw_line.strip()
            if line.startswith("KEY TAKEAWAYS"):
                mode = "takeaways"
                continue
            if line.startswith("BOX 1"):
                mode = "box1"
            elif line.startswith("BOX 2"):
                mode = "box2"
            elif line.startswith(("별첨", "Annex")):
                mode = "appendix"
            if line in KO_CHAPTERS:
                continue
            m = PARA.match(line)
            if mode in ("front", "takeaways", "para") and m and int(m.group(1)) == expected:
                mode, cur = "para", expected
                paras[cur] = {"text": raw_line, "pages": {pno}}
                expected += 1
                continue
            sep = "\n" if en and line.startswith(("■", "▪")) else ""
            if mode == "takeaways":
                takeaways.append(sep + raw_line)
            elif mode == "para" and cur:
                paras[cur]["text"] += sep + raw_line
                paras[cur]["pages"].add(pno)
            elif mode == "box1":
                box1.append(raw_line + ("\n" if en and line.startswith("BOX") else ""))
            elif mode == "box2":
                box2.append(raw_line + ("\n" if en and line.startswith("BOX") else ""))

    offset = cfg()["offset"]

    def page_range(ps: set[int]) -> str:
        a, b = offset + min(ps), offset + max(ps)
        return t(f"{a}–{b}쪽", f"pp. {a}–{b}")

    docs = []
    for doc_id, kind, rng, title_ko, title_en in SECTIONS:
        title = title_en if en else title_ko
        if kind == "takeaways":
            body, where = "".join(takeaways), t(f"KEY TAKEAWAYS, {offset + 1}쪽", f"Key takeaways, p. {offset + 1}")
        elif kind == "box2":
            body, where = "".join(box2), "BOX 2"
        else:
            nums = range(rng[0], rng[1] + 1)
            parts = [paras[n]["text"] for n in nums if n in paras]
            pages_used = set().union(*(paras[n]["pages"] for n in nums if n in paras))
            where = t(f"문단 {rng[0]}–{rng[1]}, ", f"paragraphs {rng[0]}–{rng[1]}, ") + page_range(pages_used)
            if kind == "para+box1":
                parts.append("\n\n[BOX 1] " + "".join(box1))
                where += " + BOX 1"
            body = "\n\n".join(parts)
        body = re.sub(r"[ \t]+", " ", body).replace("▢", "\n▢").replace("▪", "\n▪")
        if en:  # 영문판 요약의 로마 숫자 항목(I. II. …)을 줄 바꿈
            body = re.sub(r"\s(?=(?:I|II|III|IV|V|VI|VII)\. [A-Z])", "\n", body)
        docs.append({"doc_id": doc_id, "title": title, "where": where, "text": body.strip()})
    return docs


def write_docs(docs: list[dict], out_dir: Path | None = None) -> None:
    out_dir = out_dir or data_dir() / "docs"
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.md"):
        old.unlink()
    label = t("출처", "Source")
    for d in docs:
        slug = re.sub(r"[^0-9A-Za-z가-힣]+", "_", d["title"]).strip("_")[:24]
        (out_dir / f"{d['doc_id']}_{slug}.md").write_text(
            f"# {d['title']}\n\n> {label}: {cfg()['source']} — {d['where']}\n\n{d['text']}\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# 처음 실행할 때: PDF 내려받기 → 문서 생성
# ---------------------------------------------------------------------------
def download_pdf(lang: str | None = None) -> Path:
    """한국은행 공식 링크에서 보고서 PDF 를 내려받는다 (이미 있으면 그대로 사용)."""
    c = cfg(lang)
    path = c["pdf"]
    if path.exists() and path.stat().st_size > 100_000:
        return path
    import urllib.request
    path.parent.mkdir(parents=True, exist_ok=True)
    print(t("보고서 PDF 를 한국은행 홈페이지에서 내려받습니다…", "Downloading the report PDF from the Bank of Korea website…")
          + f"\n  {c['url']}")
    try:
        req = urllib.request.Request(c["url"], headers={"User-Agent": "Mozilla/5.0 (graphrag-live-lab)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        if not data.startswith(b"%PDF"):
            raise ValueError("not a PDF response")
        path.write_bytes(data)
    except Exception as e:
        raise SystemExit(t(
            f"PDF 를 자동으로 받지 못했습니다 ({e}).\n아래 게시물에서 「{c['file_label']}」를 직접 받아\n"
            f"  {path}\n로 저장한 뒤 다시 실행하세요.\n  {c['page']}",
            f"Could not download the PDF automatically ({e}).\nDownload \"{c['file_label']}\" from the page below,\n"
            f"save it as\n  {path}\nand run again.\n  {c['page']}"))
    print(t("  저장", "  Saved") + f": {path} ({path.stat().st_size / 1e6:.1f} MB)")
    return path


def ensure_docs() -> None:
    """현재 언어의 data/<lang>/docs 가 비어 있으면 PDF 를 받아 주제별 문서를 만든다 (실습 00 과 같은 과정)."""
    if any((data_dir() / "docs").glob("*.md")):
        return
    download_pdf()
    docs = split_sections(load_pages())
    write_docs(docs)
    print(t(f"  주제별 문서 {len(docs)}개를 data/{get_lang()}/docs 에 만들었습니다.",
            f"  Built {len(docs)} topic documents in data/{get_lang()}/docs."))
