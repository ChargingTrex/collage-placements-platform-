"""
Create the MongoDB `$vectorSearch` index for profile vectors.

    python manage.py init_vector_index            # dims from EMBED_MODEL
    python manage.py init_vector_index --dims 768

The dimension is asked of the embedding model itself when the LLM is up, so
the index always matches the vectors it will hold. The local store needs no
index; on it this command says so and exits.
"""

from django.core.management.base import BaseCommand, CommandError

from matching import llm
from matching.embeddings import get_embedder
from matching.vectorstore import MongoVectorStore, get_vector_store


class Command(BaseCommand):
    help = "Create the MongoDB vector search index for profile embeddings."

    def add_arguments(self, parser):
        parser.add_argument("--dims", type=int, help="Vector dimensions (default: probe EMBED_MODEL).")

    def handle(self, *args, dims=None, **options):
        store = get_vector_store()
        if not isinstance(store, MongoVectorStore):
            self.stdout.write(f"Vector store is '{store.name}'; it needs no index.")
            return

        if dims is None:
            embedder = get_embedder()
            if embedder is None:
                raise CommandError("LLM is disabled; pass --dims explicitly.")
            try:
                dims = len(embedder.embed("dimension probe"))
            except llm.LLMUnavailable as exc:
                raise CommandError(f"Could not reach the embedding model: {exc}") from exc

        store.create_index(dims)
        self.stdout.write(self.style.SUCCESS(f"Created vector index ({dims} dimensions)."))
