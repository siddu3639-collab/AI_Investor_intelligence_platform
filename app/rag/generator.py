from app.clients.azure_openai import generate_answer
from app.rag.prompts import SYSTEM_PROMPT, build_user_prompt

NO_EVIDENCE_MESSAGE = (
    "I could not find relevant information in the indexed company reports, "
    "so I can't answer that reliably. Try rephrasing the question or check "
    "that the right report has been uploaded."
)


def generate_investor_insight(question: str, documents: list[dict]) -> str:
    if not documents:
        return NO_EVIDENCE_MESSAGE

    prompt = build_user_prompt(question, documents)
    return generate_answer(SYSTEM_PROMPT, prompt)
