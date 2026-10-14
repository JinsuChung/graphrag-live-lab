"""실습과 라이브 실험실이 함께 쓰는 프롬프트 (언어별).  Prompts shared by the labs and the live app."""
from langchain_core.prompts import ChatPromptTemplate

from common import get_lang


class ByLang:
    """언어별 프롬프트 묶음. 현재 언어(DATA_LANG)의 템플릿처럼 동작한다 (.invoke, .format, | llm 등)."""

    def __init__(self, **templates):
        self.templates = templates

    @property
    def current(self) -> ChatPromptTemplate:
        return self.templates[get_lang()]

    def __getattr__(self, name):
        return getattr(self.current, name)

    def __or__(self, other):
        return self.current | other


VECTOR_PROMPT = ByLang(
    ko=ChatPromptTemplate.from_template(
        "다음 문서만 근거로 질문에 답하세요. 근거 문서 번호를 함께 쓰고, 문서에 없으면 모른다고 답하세요.\n\n"
        "# 문서\n{context}\n\n# 질문\n{question}"),
    en=ChatPromptTemplate.from_template(
        "Answer the question using only the documents below. Cite the document ids you rely on, "
        "and say you don't know if the documents do not contain the answer.\n\n"
        "# Documents\n{context}\n\n# Question\n{question}"),
)

GRAPH_PROMPT = ByLang(
    ko=ChatPromptTemplate.from_template(
        "아래 [지식그래프 관계]와 [원문]만 근거로 질문에 답하세요. 여러 사실을 연결해야 하면 "
        "추론 경로를 '→' 로 보여 주세요. 근거가 없으면 모른다고 답하세요.\n\n"
        "# 지식그래프 관계\n{triples}\n\n# 원문\n{docs}\n\n# 질문\n{question}"),
    en=ChatPromptTemplate.from_template(
        "Answer the question using only the [knowledge graph relations] and [source text] below. If you need to "
        "connect several facts, show the reasoning path with '→'. Say you don't know if there is no evidence.\n\n"
        "# Knowledge graph relations\n{triples}\n\n# Source text\n{docs}\n\n# Question\n{question}"),
)


def format_docs(docs) -> str:
    """LangChain Document 리스트 → '[doc01] 본문' 형식 문자열."""
    return "\n\n".join(f"[{d.metadata['doc_id']}] {d.page_content}" for d in docs)
