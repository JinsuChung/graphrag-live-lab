"""실습과 라이브 실험실이 함께 쓰는 답변 프롬프트."""
from langchain_core.prompts import ChatPromptTemplate

VECTOR_PROMPT = ChatPromptTemplate.from_template(
    "다음 문서만 근거로 질문에 답하세요. 근거 문서 번호를 함께 쓰고, 문서에 없으면 모른다고 답하세요.\n\n"
    "# 문서\n{context}\n\n# 질문\n{question}"
)

GRAPH_PROMPT = ChatPromptTemplate.from_template(
    "아래 [지식그래프 관계]와 [원문]만 근거로 질문에 답하세요. 여러 사실을 연결해야 하면 "
    "추론 경로를 '→' 로 보여 주세요. 근거가 없으면 모른다고 답하세요.\n\n"
    "# 지식그래프 관계\n{triples}\n\n# 원문\n{docs}\n\n# 질문\n{question}"
)


def format_docs(docs) -> str:
    """LangChain Document 리스트 → '[doc01] 본문' 형식 문자열."""
    return "\n\n".join(f"[{d.metadata['doc_id']}] {d.page_content}" for d in docs)
