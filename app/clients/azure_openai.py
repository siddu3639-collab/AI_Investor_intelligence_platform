from functools import lru_cache

from openai import OpenAI, BadRequestError

from app.config import settings

_skip_temperature = False


@lru_cache
def get_client() -> OpenAI:
    endpoint = settings.azure_openai_endpoint.rstrip("/")

    if not endpoint.endswith("/openai/v1"):
        endpoint += "/openai/v1"

    return OpenAI(
        base_url=endpoint + "/",
        api_key=settings.azure_openai_api_key,
        max_retries=5,
    )


@lru_cache
def get_embedding_client() -> OpenAI:
    # Use the resource-level endpoint for embeddings.
    endpoint = settings.azure_openai_endpoint.split("/api/projects/")[0].rstrip("/")
    return OpenAI(
        base_url=endpoint + "/openai/v1/",
        api_key=settings.azure_openai_api_key,
        max_retries=5,
    )



def create_embeddings(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    client = get_embedding_client()
    size = settings.embedding_batch_size
    vectors: list[list[float]] = []

    for start in range(0, len(texts), size):
        batch = texts[start:start + size]
        response = client.embeddings.create(
            model=settings.azure_openai_embedding_deployment,
            input=batch,
        )
        # The API returns items tagged with their position; sort to be safe.
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors.extend(item.embedding for item in ordered)

    got = len(vectors[0])
    if got != settings.embedding_dimensions:
        raise ValueError(
            f"Embedding model returned {got} dimensions but EMBEDDING_DIMENSIONS "
            f"is {settings.embedding_dimensions}. Fix the .env value and recreate "
            f"the search index (python -m scripts.create_search_index --recreate)."
        )
    return vectors


def create_embedding(text: str) -> list[float]:
    return create_embeddings([text])[0]


def generate_answer(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.2,
    json_mode: bool = False,
) -> str:
   
    global _skip_temperature

    request = {
        "model": settings.azure_openai_chat_deployment,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if json_mode:
        request["response_format"] = {"type": "json_object"}
    if not _skip_temperature:
        request["temperature"] = temperature

    client = get_client()
    try:
        response = client.chat.completions.create(**request)
    except BadRequestError as exc:
        if "temperature" not in request or "temperature" not in str(exc).lower():
            raise
        _skip_temperature = True
        request.pop("temperature")
        response = client.chat.completions.create(**request)

    return response.choices[0].message.content or ""
