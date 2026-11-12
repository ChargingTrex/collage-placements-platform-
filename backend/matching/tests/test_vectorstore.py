"""
Embeddings and the two vector stores.

The local store runs for real against the test database. The MongoDB store
runs against a fake collection that records what it was sent, so its query
shape and score conversion are pinned without a server. A real-MongoDB test
runs only when MONGO_URI is set.
"""

import os
from io import StringIO

import pytest

from matching import vectorstore
from matching.embeddings import Embedder, cosine, get_embedder, normalise
from matching.llm import LLMUnavailable
from matching.testing import FakeLLMClient, fake_embedding
from matching.vectorstore import (
    LocalVectorStore,
    MongoVectorStore,
    get_vector_store,
    matches_filters,
    mongo_filter,
    reset_vector_store,
    vector_index_definition,
)


class TestEmbeddings:
    def test_vectors_come_back_unit_length(self):
        vector = Embedder(FakeLLMClient()).embed("python django postgres")

        assert abs(sum(v * v for v in vector) - 1.0) < 1e-9

    def test_shared_vocabulary_scores_higher(self):
        embedder = Embedder(FakeLLMClient())
        jd = embedder.embed("backend python django postgresql")

        close = cosine(jd, embedder.embed("python django developer postgresql"))
        far = cosine(jd, embedder.embed("solidworks catia sheet metal"))

        assert close > far

    def test_a_down_server_gives_none_from_try_embed(self):
        assert Embedder(FakeLLMClient(down=True)).try_embed("text") is None

    def test_a_down_server_raises_from_embed(self):
        with pytest.raises(LLMUnavailable):
            Embedder(FakeLLMClient(down=True)).embed("text")

    def test_no_embedder_when_the_llm_is_disabled(self, settings):
        settings.LLM = {**settings.LLM, "ENABLED": False}

        assert get_embedder() is None

    def test_cosine_of_mismatched_dimensions_is_zero(self):
        assert cosine([1.0, 0.0], [1.0, 0.0, 0.0]) == 0.0

    def test_normalise_leaves_a_zero_vector_alone(self):
        assert normalise([0.0, 0.0]) == [0.0, 0.0]

    @pytest.mark.parametrize(
        "reply",
        [
            [["a", "b"]],          # not numbers
            [[None, 0.1]],         # not numbers either
            [[0.1, 0.2], [0.1]],   # unequal lengths within one reply
            [[], []],              # empty vectors
        ],
    )
    def test_a_malformed_embeddings_reply_is_unavailable(self, reply):
        client = FakeLLMClient()
        client.embed = lambda texts: reply

        embedder = Embedder(client)
        with pytest.raises(LLMUnavailable):
            embedder.embed_many(["one", "two"][: len(reply)])
        assert embedder.try_embed("one") is None


class TestFilters:
    META = {"department": "CE", "batch": 2026, "skills": ["python", "django"], "experience_months": 18}

    @pytest.mark.parametrize(
        "filters,expected",
        [
            (None, True),
            ({"department": "CE"}, True),
            ({"department": "ME"}, False),
            ({"skills": "python"}, True),
            ({"skills": "react"}, False),
            ({"skills": {"in": ["react", "django"]}}, True),
            ({"skills": {"in": ["react"]}}, False),
            ({"experience_months": {"gte": 12}}, True),
            ({"experience_months": {"gte": 24}}, False),
            ({"experience_months": {"lte": 12}}, False),
            ({"categories": {"in": ["Backend Engineer"]}}, False),
        ],
    )
    def test_the_local_reading_of_the_filter_dialect(self, filters, expected):
        assert matches_filters(self.META, filters) is expected

    def test_the_mongo_reading_of_the_same_dialect(self):
        query = mongo_filter(
            "nomic", {"department": "CE", "skills": {"in": ["python"]}, "experience_months": {"gte": 12}}
        )

        assert query == {
            "$and": [
                {"model": {"$eq": "nomic"}},
                {"meta.department": {"$eq": "CE"}},
                {"meta.skills": {"$in": ["python"]}},
                {"meta.experience_months": {"$gte": 12}},
            ]
        }

    def test_with_no_filters_only_the_model_is_filtered(self):
        assert mongo_filter("nomic", None) == {"model": {"$eq": "nomic"}}


@pytest.mark.django_db
class TestLocalStore:
    @pytest.fixture
    def store(self):
        return LocalVectorStore()

    def test_nearest_first(self, store):
        store.upsert("backend", fake_embedding("python django postgresql api"), {"department": "CE"}, "m")
        store.upsert("mech", fake_embedding("solidworks catia sheet metal"), {"department": "ME"}, "m")

        results = store.search(fake_embedding("django python backend"), k=2, model="m")

        assert [doc_id for doc_id, _ in results] == ["backend", "mech"]
        assert results[0][1] > results[1][1]

    def test_filters_apply_before_ranking(self, store):
        store.upsert("backend", fake_embedding("python django"), {"department": "CE"}, "m")
        store.upsert("mech", fake_embedding("solidworks"), {"department": "ME"}, "m")

        results = store.search(fake_embedding("python django"), k=5, model="m", filters={"department": "ME"})

        assert [doc_id for doc_id, _ in results] == ["mech"]

    def test_vectors_from_another_model_are_never_mixed_in(self, store):
        store.upsert("old", fake_embedding("python"), {}, "old-model")
        store.upsert("new", fake_embedding("python"), {}, "new-model")

        assert [d for d, _ in store.search(fake_embedding("python"), k=5, model="new-model")] == ["new"]

    def test_upsert_replaces_and_delete_removes(self, store):
        store.upsert("a", fake_embedding("python"), {"department": "CE"}, "m")
        store.upsert("a", fake_embedding("java"), {"department": "IT"}, "m")

        vector, meta, model = store.get("a")
        assert meta == {"department": "IT"} and vector == fake_embedding("java")

        store.delete("a")
        assert store.get("a") is None

    def test_only_filter_fields_are_stored(self, store):
        """Resume text or contact details must never reach a vector store."""
        store.upsert("a", fake_embedding("x"), {"department": "CE", "resume_text": "...", "email": "a@b.c"}, "m")

        assert store.get("a")[1] == {"department": "CE"}

    def test_update_meta_merges_without_re_embedding(self, store):
        store.upsert("a", fake_embedding("python"), {"department": "CE"}, "m")

        store.update_meta("a", {"categories": ["Backend Engineer"], "phone": "999"})

        assert store.get("a")[1] == {"department": "CE", "categories": ["Backend Engineer"]}

    def test_k_limits_the_results(self, store):
        for i in range(5):
            store.upsert(f"p{i}", fake_embedding(f"python skill{i}"), {}, "m")

        assert len(store.search(fake_embedding("python"), k=3, model="m")) == 3


class FakeCollection:
    """Records what MongoVectorStore sends; replies with canned documents."""

    def __init__(self, aggregate_reply=None):
        self.aggregate_reply = aggregate_reply or []
        self.calls = []

    def aggregate(self, pipeline):
        self.calls.append(("aggregate", pipeline))
        return iter(self.aggregate_reply)

    def replace_one(self, query, doc, upsert=False):
        self.calls.append(("replace_one", query, doc, upsert))

    def find_one(self, query):
        self.calls.append(("find_one", query))
        return None

    def delete_one(self, query):
        self.calls.append(("delete_one", query))

    def update_one(self, query, update):
        self.calls.append(("update_one", query, update))

    def create_search_index(self, model):
        self.calls.append(("create_search_index", model))


class TestMongoStore:
    def test_search_sends_a_vector_search_pipeline(self):
        collection = FakeCollection([{"_id": "p1", "score": 0.9}])
        store = MongoVectorStore(collection, "idx")

        store.search([0.1, 0.2], k=5, model="nomic", filters={"department": "CE"})

        stage = collection.calls[0][1][0]["$vectorSearch"]
        assert stage["index"] == "idx"
        assert stage["limit"] == 5
        assert stage["numCandidates"] >= 50
        assert stage["filter"]["$and"][0] == {"model": {"$eq": "nomic"}}

    def test_mongos_cosine_score_is_converted_back(self):
        """Mongo reports (1 + cos) / 2; both stores must return cos."""
        store = MongoVectorStore(FakeCollection([{"_id": "p1", "score": 0.9}]), "idx")

        [(doc_id, score)] = store.search([0.1], k=1, model="m")

        assert doc_id == "p1" and score == pytest.approx(0.8)

    def test_upsert_stores_no_resume_text(self):
        collection = FakeCollection()

        MongoVectorStore(collection, "idx").upsert(
            "p1", [0.1], {"department": "CE", "resume_text": "secret"}, "m"
        )

        _, query, doc, upsert = collection.calls[0]
        assert upsert and query == {"_id": "p1"}
        assert doc["meta"] == {"department": "CE"}
        assert "secret" not in str(doc)

    def test_the_index_declares_every_filter_field(self):
        definition = vector_index_definition(768)

        paths = {field["path"] for field in definition["fields"]}
        assert {"vector", "model", "meta.department", "meta.skills", "meta.categories"} <= paths
        assert definition["fields"][0]["numDimensions"] == 768


class TestInitVectorIndex:
    """`manage.py init_vector_index`, against a fake collection."""

    @pytest.fixture
    def mongo(self, monkeypatch):
        from matching.management.commands import init_vector_index

        collection = FakeCollection()
        monkeypatch.setattr(
            init_vector_index, "get_vector_store", lambda: MongoVectorStore(collection, "profile_idx")
        )
        return collection

    @staticmethod
    def _index(collection) -> dict:
        [(_, model)] = [call for call in collection.calls if call[0] == "create_search_index"]
        return model if isinstance(model, dict) else model.document

    def test_the_local_store_needs_no_index(self, settings):
        from django.core.management import call_command

        settings.VECTOR_STORE = {**settings.VECTOR_STORE, "BACKEND": "local"}
        reset_vector_store()
        out = StringIO()
        try:
            call_command("init_vector_index", stdout=out)
        finally:
            reset_vector_store()

        assert "needs no index" in out.getvalue()

    def test_explicit_dims_create_the_index(self, mongo):
        from django.core.management import call_command

        call_command("init_vector_index", "--dims", "768", stdout=StringIO())

        index = self._index(mongo)
        assert index["name"] == "profile_idx"
        assert index["type"] == "vectorSearch"
        assert index["definition"]["fields"][0]["numDimensions"] == 768

    def test_without_dims_a_disabled_llm_is_an_error(self, mongo, settings):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        settings.LLM = {**settings.LLM, "ENABLED": False}

        with pytest.raises(CommandError):
            call_command("init_vector_index")
        assert not mongo.calls

    def test_without_dims_the_embedding_model_is_probed(self, mongo, monkeypatch):
        from django.core.management import call_command

        from matching.management.commands import init_vector_index
        from matching.testing import EMBED_DIMS

        monkeypatch.setattr(init_vector_index, "get_embedder", lambda: Embedder(FakeLLMClient()))

        call_command("init_vector_index", stdout=StringIO())

        assert self._index(mongo)["definition"]["fields"][0]["numDimensions"] == EMBED_DIMS


class TestSelection:
    @pytest.fixture(autouse=True)
    def _fresh(self):
        reset_vector_store()
        yield
        reset_vector_store()

    def test_auto_without_a_uri_is_local(self, settings):
        settings.VECTOR_STORE = {**settings.VECTOR_STORE, "BACKEND": "auto", "MONGO_URI": ""}

        assert get_vector_store().name == "local"

    def test_auto_with_an_unreachable_uri_falls_back_to_local(self, settings, monkeypatch):
        settings.VECTOR_STORE = {**settings.VECTOR_STORE, "BACKEND": "auto", "MONGO_URI": "mongodb://nowhere"}

        def unreachable(cls):
            raise ConnectionError("no server")

        monkeypatch.setattr(MongoVectorStore, "from_settings", classmethod(unreachable))

        assert get_vector_store().name == "local"

    def test_an_unknown_backend_is_an_error(self, settings):
        settings.VECTOR_STORE = {**settings.VECTOR_STORE, "BACKEND": "pinecone"}

        with pytest.raises(ValueError):
            get_vector_store()


@pytest.mark.skipif(not os.getenv("MONGO_URI"), reason="needs a real MongoDB (set MONGO_URI)")
def test_real_mongo_round_trip(settings):  # pragma: no cover - needs a server
    settings.VECTOR_STORE = {**settings.VECTOR_STORE, "BACKEND": "mongo", "MONGO_URI": os.environ["MONGO_URI"]}
    reset_vector_store()
    store = vectorstore.get_vector_store()
    store.upsert("roundtrip-test", fake_embedding("python"), {"department": "CE"}, "test-model")
    try:
        assert store.get("roundtrip-test")[1] == {"department": "CE"}
    finally:
        store.delete("roundtrip-test")
        reset_vector_store()
