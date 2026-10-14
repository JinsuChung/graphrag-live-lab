# %% [markdown]
# # 실습 00. PDF → 실습 문서 만들기 (데이터 준비)
# 교재 PDF(한국은행 「혁신과 경제성장」)를 공식 링크에서 받아 LangChain PyPDFLoader 로 읽고,
# ① 정제: 차트 숫자·머리글·각주 등 잡음 줄 제거
# ② 섹션 분할: 보고서의 문단 번호(1~56)와 BOX 를 기준으로 주제별 문서 19개로 묶기
# ③ data/docs/*.md 로 저장 → 이후 모든 실습의 입력
# 구현은 pdf_prep.py 에 있다. LLM/API 키 없이 실행된다.

# %%
from collections import Counter

from common import header
from pdf_prep import PDF_PATH, clean_page, download_pdf, load_pages, split_sections, write_docs

# %% ① 로드 --------------------------------------------------------------
download_pdf()  # 없으면 한국은행 공식 링크에서 받는다 (저작권 때문에 저장소에는 PDF 를 넣지 않음)
pages = load_pages()
header(f"PDF 로드: {PDF_PATH.name}")
print(f"{len(pages)}쪽, 총 {sum(len(p) for p in pages):,}자")
print("\n[2쪽 원문 앞부분]\n" + pages[1][:400])

# %% ② 정제 --------------------------------------------------------------
header("정제: 지운 줄의 이유별 개수")
reasons = Counter()
for p in pages:
    _, removed = clean_page(p)
    reasons.update(r["reason"] for r in removed)
for r, n in reasons.most_common():
    print(f"  {r:16} {n:5}줄")
kept, removed = clean_page(pages[3])
print("\n[4쪽에서 지운 줄 예시]")
for r in removed[:12]:
    print(f"  ✗ ({r['reason']}) {r['line'][:50]}")

# %% ③ 섹션 분할 + 저장 ---------------------------------------------------
docs = split_sections(pages)
write_docs(docs)
header(f"주제별 문서 {len(docs)}개 → data/docs/")
for d in docs:
    print(f"  {d['doc_id']}  {len(d['text']):5}자  {d['title']}  ({d['where']})")
print("\n생각해 볼 점: 정제 규칙이 차트 라벨 일부를 놓치거나, 문장 일부를 지우지는 않았나?")
print("PDF 전처리 품질이 이후 청크·임베딩·그래프 추출 품질을 모두 좌우한다.")
