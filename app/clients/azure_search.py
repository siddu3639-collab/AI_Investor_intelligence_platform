from functools import lru_cache

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

from app.config import settings

SELECT_FIELDS = ["id", "company", "report_year", "page", "content", "source"]


@lru_cache
def get_search_client() -> SearchClient:
    return SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_index,
        credential=AzureKeyCredential(settings.azure_search_api_key),
    )


def upload_chunks(documents: list[dict], batch_size: int = 500) -> None:
    client = get_search_client()

    for start in range(0, len(documents), batch_size):
        batch = documents[start:start + batch_size]
        results = client.upload_documents(documents=batch)

        failed = [r for r in results if not r.succeeded]
        if failed:
            raise RuntimeError(
                f"Azure AI Search rejected {len(failed)} of {len(batch)} chunks "
                f"(first error: {failed[0].error_message})"
            )


def delete_report_chunks(report_id: int) -> int:
    """Remove every chunk that belongs to one report. Returns how many were deleted."""
    client = get_search_client()
    deleted = 0

    # A query returns at most 1000 hits, so keep going until nothing is left.
    for _ in range(50):
        hits = list(
            client.search(
                search_text="*",
                filter=f"report_id eq {int(report_id)}",
                select=["id"],
                top=1000,
            )
        )
        if not hits:
            break
        client.delete_documents(documents=[{"id": hit["id"]} for hit in hits])
        deleted += len(hits)

    return deleted


def hybrid_search(
    query_text: str,
    query_vector: list[float],
    top_k: int,
    odata_filter: str | None = None,
) -> list[dict]:
    vector_query = VectorizedQuery(
        vector=query_vector,
        k_nearest_neighbors=top_k,
        fields="content_vector",
    )

    results = get_search_client().search(
        search_text=query_text,
        vector_queries=[vector_query],
        filter=odata_filter,
        select=SELECT_FIELDS,
        top=top_k,
    )

    return [
        {
            "id": hit["id"],
            "company": hit["company"],
            "report_year": hit.get("report_year"),
            "page": hit.get("page"),
            "content": hit["content"],
            "source": hit.get("source"),
            "score": hit.get("@search.score"),
        }
        for hit in results
    ]
