# %% [markdown]
# # 실습 00. PDF → 실습 문서 만들기 (데이터 준비)  /  Lab 00. From PDF to lab documents
# 교재 PDF(한국은행 「혁신과 경제성장」)를 공식 링크에서 받아 LangChain PyPDFLoader 로 읽고,
# ① 정제: 차트 숫자·머리글·각주 등 잡음 줄 제거 (국문판: 글자 규칙, 영문판: 글꼴 크기)
# ② 섹션 분할: 보고서의 문단 번호(1~56)와 BOX 를 기준으로 주제별 문서 19개로 묶기
# ③ data/<언어>/docs/*.md 로 저장 → 이후 모든 실습의 입력
# 구현은 pdf_prep.py 에 있다. LLM/API 키 없이 실행된다. / Runs without an LLM.

# %%
from collections import Counter

from common import get_lang, header, t
from pdf_prep import clean, download_pdf, load_pages, pdf_path, split_sections, write_docs

# %% ① 로드 --------------------------------------------------------------
download_pdf()  # 없으면 한국은행 공식 링크에서 받는다 (저작권 때문에 저장소에는 PDF 를 넣지 않음)
pages = load_pages()
header(t(f"PDF 로드: {pdf_path().name}", f"Loaded PDF: {pdf_path().name}"))
print(t(f"{len(pages)}쪽, 총 {sum(len(p) for p in pages):,}자", f"{len(pages)} pages, {sum(len(p) for p in pages):,} characters"))
print(t("\n[2쪽 원문 앞부분]\n", "\n[Start of page 2]\n") + pages[1][:400])

# %% ② 정제 --------------------------------------------------------------
header(t("정제: 지운 줄의 이유별 개수", "Cleaning: removed lines by reason"))
reasons = Counter()
for pi in range(len(pages)):
    _, removed = clean(pi, pages)
    reasons.update(r["reason"].split(" · ")[0] for r in removed)
for r, n in reasons.most_common():
    print(f"  {r:40} {n:5}")
_, removed = clean(3, pages)
print(t("\n[4쪽에서 지운 줄 예시]", "\n[Removed lines on page 4]"))
for r in removed[:12]:
    print(f"  ✗ ({r['reason']}) {r['line'][:50]}")

# %% ③ 섹션 분할 + 저장 ---------------------------------------------------
docs = split_sections(pages)
write_docs(docs)
header(t(f"주제별 문서 {len(docs)}개 → data/{get_lang()}/docs/", f"{len(docs)} topic documents → data/{get_lang()}/docs/"))
for d in docs:
    print(f"  {d['doc_id']}  {len(d['text']):5}  {d['title']}  ({d['where']})")
print(t("\n생각해 볼 점: 정제 규칙이 차트 라벨 일부를 놓치거나, 문장 일부를 지우지는 않았나?\n"
        "PDF 전처리 품질이 이후 청크·임베딩·그래프 추출 품질을 모두 좌우한다.",
        "\nThink: did the cleaning rules miss chart labels or drop parts of sentences?\n"
        "Preprocessing quality drives the quality of every later step: chunks, embeddings, graph extraction."))
