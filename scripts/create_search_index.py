"""
Create (or update) the Azure AI Search index.

    python -m scripts.create_search_index
    python -m scripts.create_search_index --recreate   # drop it first (needed if dimensions change)
"""
import argparse

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    HnswParameters,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
    VectorSearch,
    VectorSearchAlgorithmMetric,
    VectorSearchProfile,
)

from app.config import settings


def build_index() -> SearchIndex:
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SimpleField(name="company_id", type=SearchFieldDataType.Int32, filterable=True),
        SearchableField(name="company", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="report_id", type=SearchFieldDataType.Int32, filterable=True),
        SimpleField(name="report_year", type=SearchFieldDataType.Int32, filterable=True),
        SimpleField(name="page", type=SearchFieldDataType.Int32, filterable=True),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=settings.embedding_dimensions,
            vector_search_profile_name="financial-vector-profile",
        ),
        SimpleField(name="source", type=SearchFieldDataType.String, filterable=True),
    ]

    vector_search = VectorSearch(
        algorithms=[
            # HNSW = approximate nearest-neighbour graph: fast even with millions
            # of chunks. Cosine is the right metric for OpenAI embeddings.
            HnswAlgorithmConfiguration(
                name="financial-hnsw",
                parameters=HnswParameters(metric=VectorSearchAlgorithmMetric.COSINE),
            )
        ],
        profiles=[
            VectorSearchProfile(
                name="financial-vector-profile",
                algorithm_configuration_name="financial-hnsw",
            )
        ],
    )

    return SearchIndex(
        name=settings.azure_search_index, fields=fields, vector_search=vector_search
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recreate", action="store_true", help="delete the index first")
    args = parser.parse_args()

    client = SearchIndexClient(
        endpoint=settings.azure_search_endpoint,
        credential=AzureKeyCredential(settings.azure_search_api_key),
    )

    if args.recreate:
        try:
            client.delete_index(settings.azure_search_index)
            print(f"Deleted index: {settings.azure_search_index}")
        except Exception as exc:  # didn't exist yet
            print(f"(nothing to delete: {exc.__class__.__name__})")

    result = client.create_or_update_index(build_index())
    print(f"Index ready: {result.name} ({settings.embedding_dimensions}-dim vectors)")


if __name__ == "__main__":
    main()
