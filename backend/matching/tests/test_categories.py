"""
Role categories derived from recruiters' job descriptions (plan Task 7).

A category is fed only by JDs the LLM has read (a `canonical_role`); with
the LLM off none are created, and nothing is invented.
"""

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.management import call_command

from matching import categories
from matching.admin import RoleCategoryAdmin
from matching.llm import JobFacts
from matching.models import RoleCategory
from matching.samples import RELEVANT_KEYS, SAMPLE_RESUMES
from matching.skills import find_in_text
from matching.testing import fake_embedding, job_reply


def facts(**overrides):
    return JobFacts(data=job_reply(**overrides), model="fake-llama")


@pytest.mark.django_db
class TestRecordJobDescription:
    def test_the_first_jd_for_a_role_creates_its_category(self):
        category = categories.record_job_description(facts(), [1.0, 0.0], model="fake-embed")
        assert category.name == "Backend Engineer"
        assert category.jd_count == 1
        assert category.skill_weights == {"Python": 1, "Django": 1, "PostgreSQL": 1}
        assert category.centroid == [1.0, 0.0]
        assert category.centroid_model == "fake-embed"

    def test_a_second_jd_with_the_same_role_merges_case_and_space_insensitively(self):
        categories.record_job_description(facts(), None)
        merged = categories.record_job_description(
            facts(canonical_role="  backend   ENGINEER ", title="Senior Backend Engineer",
                  required_skills=["Python", "Docker"]),
            None,
        )
        assert RoleCategory.objects.count() == 1
        assert merged.jd_count == 2
        assert merged.skill_weights == {"Python": 2, "Django": 1, "PostgreSQL": 1, "Docker": 1}
        assert "Senior Backend Engineer" in merged.aliases

    def test_a_role_matching_an_alias_merges_into_that_category(self):
        categories.record_job_description(facts(title="Python Backend Developer"), None)
        merged = categories.record_job_description(facts(canonical_role="Python Backend Developer"), None)
        assert RoleCategory.objects.count() == 1
        assert merged.name == "Backend Engineer"
        assert merged.jd_count == 2

    def test_a_different_role_creates_a_different_category(self):
        categories.record_job_description(facts(), None)
        categories.record_job_description(facts(canonical_role="Data Analyst", title="Data Analyst"), None)
        assert set(RoleCategory.objects.values_list("name", flat=True)) == {"Backend Engineer", "Data Analyst"}

    def test_skills_are_counted_by_their_canonical_name(self):
        category = categories.record_job_description(
            facts(required_skills=["Postgres", "PostgreSQL", "DRF"]), None
        )
        assert category.skill_weights == {"PostgreSQL": 1, "Django REST Framework": 1}

    def test_the_centroid_is_the_running_mean_of_the_jd_vectors(self):
        categories.record_job_description(facts(), [1.0, 0.0, 0.0], model="m")
        categories.record_job_description(facts(), [0.8, 0.6, 0.0], model="m")
        category = categories.record_job_description(facts(), [0.9, 0.0, 0.3], model="m")
        assert category.centroid == pytest.approx([0.9, 0.2, 0.1])
        assert category.centroid_count == 3

    def test_a_jd_without_a_vector_counts_but_leaves_the_centroid_alone(self):
        categories.record_job_description(facts(), [1.0, 0.0], model="m")
        category = categories.record_job_description(facts(), None)
        assert category.jd_count == 2
        assert category.centroid == [1.0, 0.0]
        assert category.centroid_count == 1

    def test_a_same_titled_jd_far_from_the_centroid_starts_its_own_category(self, settings):
        settings.CATEGORY = {**settings.CATEGORY, "MERGE_THRESHOLD": 0.8}
        categories.record_job_description(facts(), [1.0, 0.0], model="m")
        apart = categories.record_job_description(facts(), [0.0, 1.0], model="m")
        assert apart.name == "Backend Engineer (2)"
        assert "Backend Engineer" in apart.aliases
        # The next close one finds its own variant, not the first.
        again = categories.record_job_description(facts(), [0.1, 0.99], model="m")
        assert again.pk == apart.pk

    def test_a_close_enough_centroid_merges(self, settings):
        settings.CATEGORY = {**settings.CATEGORY, "MERGE_THRESHOLD": 0.8}
        categories.record_job_description(facts(), [1.0, 0.0], model="m")
        categories.record_job_description(facts(), [0.9, 0.1], model="m")
        assert RoleCategory.objects.count() == 1

    def test_a_centroid_from_another_model_is_replaced_not_mixed(self):
        categories.record_job_description(facts(), [1.0, 0.0], model="old")
        category = categories.record_job_description(facts(), [0.0, 1.0, 0.0], model="new")
        assert RoleCategory.objects.count() == 1
        assert category.centroid == [0.0, 1.0, 0.0]
        assert category.centroid_model == "new"
        assert category.centroid_count == 1

    @pytest.mark.parametrize("job", [None, JobFacts(data=job_reply(canonical_role="", title=""), model="x")])
    def test_without_a_canonical_role_nothing_is_recorded(self, job):
        assert categories.record_job_description(job, [1.0]) is None
        assert not RoleCategory.objects.exists()

    def test_a_hostile_role_is_cleaned_and_its_variant_still_fits_the_name_column(self, settings):
        settings.CATEGORY = {**settings.CATEGORY, "MERGE_THRESHOLD": 0.8}
        hostile = "<script>alert(1)</script>\n\t" + "A" * 5000
        first = categories.record_job_description(facts(canonical_role=hostile, title=hostile), [1.0, 0.0], model="m")
        apart = categories.record_job_description(facts(canonical_role=hostile, title=hostile), [0.0, 1.0], model="m")
        name_limit = RoleCategory._meta.get_field("name").max_length
        for category in (first, apart):
            for spelling in [category.name, *category.aliases]:
                assert "<" not in spelling and ">" not in spelling
                assert "\n" not in spelling and "\t" not in spelling
                assert "  " not in spelling
            assert len(category.name) <= name_limit
        assert len(first.name) <= categories.MAX_ROLE_CHARS
        assert first.name.startswith("alert(1) AAAA")
        assert apart.name == f"{first.name} (2)"

    def test_control_characters_and_runs_of_space_are_removed(self):
        category = categories.record_job_description(
            facts(canonical_role="Backend\x00\x1b   Engineer​", title="Senior\r\nBackend Engineer"), None
        )
        assert category.name == "Backend Engineer"
        assert "Senior Backend Engineer" in category.aliases

    @pytest.mark.parametrize("role", ["<b></b>", "\x00\x07 \n", "<img src=x onerror=alert(1)>"])
    def test_a_role_that_cleans_to_nothing_records_nothing(self, role):
        assert categories.record_job_description(facts(canonical_role=role, title=""), [1.0]) is None
        assert not RoleCategory.objects.exists()

    def test_a_cleaned_role_joins_the_category_its_clean_spelling_names(self):
        categories.record_job_description(facts(), None)
        categories.record_job_description(facts(canonical_role="<b>Backend</b> Engineer"), None)
        assert RoleCategory.objects.get().jd_count == 2


@pytest.mark.django_db
class TestCategoriseProfile:
    def test_with_no_categories_a_profile_gets_none(self):
        assert categories.categorise_profile([1.0, 0.0], ["Python", "Django"]) == []

    @pytest.fixture
    def three_roles(self):
        categories.record_job_description(facts(), [1.0, 0.0, 0.0], model="m")
        categories.record_job_description(
            facts(canonical_role="Data Analyst", title="Data Analyst", required_skills=["SQL", "pandas", "Excel"]),
            [0.0, 1.0, 0.0], model="m",
        )
        categories.record_job_description(
            facts(canonical_role="Mechanical Design Engineer", title="Design Engineer",
                  required_skills=["SolidWorks", "AutoCAD"]),
            [0.0, 0.0, 1.0], model="m",
        )

    def test_the_best_fit_comes_first(self, three_roles):
        fits = categories.categorise_profile([0.9, 0.3, 0.0], ["Django", "Postgres", "SQL", "pandas"], model="m")
        assert fits[0] == "Backend Engineer"
        assert "Mechanical Design Engineer" not in fits

    def test_skill_overlap_goes_through_the_skill_graph(self, three_roles):
        # DRF implies Django implies Python; Postgres is PostgreSQL.
        assert categories.categorise_profile(None, ["DRF", "Postgres"]) == ["Backend Engineer"]

    def test_a_weak_fit_gets_no_category(self, three_roles):
        assert categories.categorise_profile(None, ["Figma"]) == []

    def test_at_most_the_configured_number_are_returned(self, three_roles, settings):
        settings.CATEGORY = {**settings.CATEGORY, "MAX_PER_PROFILE": 1, "MIN_FIT": 0.0}
        assert len(categories.categorise_profile(None, ["Python", "SQL", "SolidWorks"])) == 1

    def test_a_vector_from_another_model_is_not_compared_with_the_centroid(self, three_roles):
        same = categories.categorise_profile([0.0, 0.0, 1.0], [], model="m")
        other = categories.categorise_profile([0.0, 0.0, 1.0], [], model="other")
        assert same == ["Mechanical Design Engineer"]
        assert other == []

    def test_the_sample_jd_category_holds_the_two_backend_samples(self):
        from matching.samples import SAMPLE_JOB_DESCRIPTION

        categories.record_job_description(facts(), fake_embedding(SAMPLE_JOB_DESCRIPTION), model="fake-embed")
        landed = {
            sample.key
            for sample in SAMPLE_RESUMES
            if "Backend Engineer"
            in categories.categorise_profile(fake_embedding(sample.text), find_in_text(sample.text), model="fake-embed")
        }
        assert landed == RELEVANT_KEYS


@pytest.mark.django_db
class TestAdmin:
    @pytest.fixture
    def request_(self, rf, admin_user):
        request = rf.post("/")
        request.user = admin_user
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def test_merging_selected_categories_folds_them_into_the_largest(self, request_):
        categories.record_job_description(facts(), [1.0, 0.0], model="m")
        categories.record_job_description(facts(), [1.0, 0.0], model="m")
        categories.record_job_description(
            facts(canonical_role="Backend Developer", title="Server Developer", required_skills=["Go"]),
            [0.0, 1.0], model="m",
        )
        admin = RoleCategoryAdmin(RoleCategory, AdminSite())
        admin.merge_selected(request_, RoleCategory.objects.all())

        [merged] = RoleCategory.objects.all()
        assert merged.name == "Backend Engineer"
        assert merged.jd_count == 3
        assert merged.skill_weights["Go"] == 1 and merged.skill_weights["Python"] == 2
        assert {"Backend Developer", "Server Developer"} <= set(merged.aliases)
        assert merged.centroid == pytest.approx([2 / 3, 1 / 3])
        assert merged.centroid_count == 3

    def test_a_merge_across_models_keeps_the_centroid_of_the_model_with_the_most_vectors(self, request_):
        for vector in ([1.0, 0.0], [1.0, 0.0], [0.8, 0.6]):
            categories.record_job_description(facts(), vector, model="m")  # A: 3 JDs on m
        categories.record_job_description(facts(canonical_role="Backend Developer", title=""), [1.0, 0.0], model="m")
        categories.record_job_description(facts(canonical_role="Server Engineer", title=""), [0.5, 0.5], model="other")
        RoleCategoryAdmin(RoleCategory, AdminSite()).merge_selected(request_, RoleCategory.objects.all())

        [merged] = RoleCategory.objects.all()
        assert merged.jd_count == 5
        assert merged.centroid_model == "m"
        assert merged.centroid_count == 4
        assert merged.centroid == pytest.approx([0.95, 0.15])  # A's and B's mean; C's is dropped

    def test_a_model_split_across_the_merged_away_categories_can_outweigh_the_target(self):
        target = RoleCategory.objects.create(name="A", jd_count=3, centroid=[1.0, 0.0], centroid_model="m", centroid_count=1)
        b = RoleCategory.objects.create(name="B", jd_count=1, centroid=[0.0, 1.0], centroid_model="other", centroid_count=1)
        c = RoleCategory.objects.create(name="C", jd_count=1, centroid=[0.0, 0.5], centroid_model="other", centroid_count=1)
        target.absorb(b, c)
        assert (target.centroid_model, target.centroid_count) == ("other", 2)
        assert target.centroid == pytest.approx([0.0, 0.75])

    def test_on_a_tie_the_targets_centroid_is_kept(self):
        target = RoleCategory.objects.create(name="A", jd_count=2, centroid=[1.0, 0.0], centroid_model="m", centroid_count=1)
        other = RoleCategory.objects.create(name="B", jd_count=1, centroid=[0.0, 1.0], centroid_model="x", centroid_count=1)
        target.absorb(other)
        assert (target.centroid, target.centroid_model, target.centroid_count) == ([1.0, 0.0], "m", 1)

    def test_a_target_with_no_centroid_takes_the_merged_ones(self):
        target = RoleCategory.objects.create(name="A", jd_count=2)
        other = RoleCategory.objects.create(name="B", jd_count=1, centroid=[0.0, 1.0], centroid_model="x", centroid_count=1)
        target.absorb(other)
        assert (target.centroid, target.centroid_model, target.centroid_count) == ([0.0, 1.0], "x", 1)

    def test_a_merged_away_name_still_routes_new_jds(self, request_):
        categories.record_job_description(facts(), None)
        categories.record_job_description(facts(canonical_role="Backend Developer", title="Backend Developer"), None)
        RoleCategoryAdmin(RoleCategory, AdminSite()).merge_selected(request_, RoleCategory.objects.all())
        categories.record_job_description(facts(canonical_role="Backend Developer"), None)
        assert RoleCategory.objects.count() == 1

    def test_renaming_keeps_the_old_name_as_an_alias(self, request_):
        category = categories.record_job_description(facts(), None)
        category.name = "Backend Developer"
        admin = RoleCategoryAdmin(RoleCategory, AdminSite())
        admin.save_model(request_, category, form=None, change=True)
        category.refresh_from_db()
        assert "Backend Engineer" in category.aliases
        assert categories.record_job_description(facts(), None).pk == category.pk

    def test_the_model_is_registered_in_the_admin(self):
        from django.contrib import admin

        assert RoleCategory in admin.site._registry


@pytest.mark.django_db
class TestSeedDemo:
    def test_with_the_llm_off_seed_demo_creates_the_demo_categories_once(self, tmp_path):
        roster = tmp_path / "roster.csv"
        roster.write_text("prn,email,full_name,department,batch,cgpa\n")
        call_command("seed_demo", roster=str(roster))
        names = set(RoleCategory.objects.values_list("name", flat=True))
        assert "Backend Engineer" in names
        assert len(names) >= 3
        counts = dict(RoleCategory.objects.values_list("name", "jd_count"))

        call_command("seed_demo", roster=str(roster))
        assert dict(RoleCategory.objects.values_list("name", "jd_count")) == counts
