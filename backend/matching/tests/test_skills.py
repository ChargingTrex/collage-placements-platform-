"""The skill graph: aliases, implications, and admin-approved alias suggestions."""

import pytest
from django.contrib.admin.sites import AdminSite

from matching import skills
from matching.admin import SkillAliasSuggestionAdmin
from matching.embeddings import Embedder
from matching.models import Skill, SkillAlias, SkillAliasSuggestion, slugify_skill
from matching.testing import FakeLLMClient


@pytest.fixture
def empty_graph(db):
    SkillAliasSuggestion.objects.all().delete()
    SkillAlias.objects.all().delete()
    Skill.objects.all().delete()
    skills.reset_skill_graph()


def make_skill(name, aliases=(), implies=()):
    skill = Skill.objects.create(name=name)
    for alias in aliases:
        SkillAlias.objects.create(skill=skill, name=alias)
    for target in implies:
        skill.implies.add(Skill.objects.get(name=target))
    return skill


class TestSlug:
    def test_the_slug_matches_the_profile_skill_slug(self):
        from profiles.models import slugify_skill as profile_slug

        for name in ["Node.js", "node js", "C++", "C#", ".NET", " .net ", "F#", "ASP.NET",
                     "Django REST Framework", "", None]:
            assert slugify_skill(name) == profile_slug(name)

    @pytest.mark.parametrize(
        "name, slug",
        [
            ("C", "c"),
            ("C++", "cplusplus"),
            ("c ++", "cplusplus"),
            ("C#", "csharp"),
            ("F#", "fsharp"),
            ("F", "f"),
            (".NET", "dotnet"),
            ("  .net", "dotnet"),
            ("NET", "net"),
            ("ASP.NET", "aspnet"),
            ("Node.js", "nodejs"),
            ("node js", "nodejs"),
            ("NodeJS", "nodejs"),
        ],
    )
    def test_plus_sharp_and_a_leading_dot_keep_skills_apart(self, name, slug):
        assert slugify_skill(name) == slug


@pytest.mark.django_db
class TestSeed:
    """The data migration's seed, as every fresh database has it."""

    @pytest.mark.parametrize(
        "alias, expected",
        [
            ("Postgres", "PostgreSQL"),
            ("JS", "JavaScript"),
            ("TS", "TypeScript"),
            ("Node", "Node.js"),
            ("NodeJS", "Node.js"),
            ("React.js", "React"),
            ("DRF", "Django REST Framework"),
            ("sklearn", "scikit-learn"),
            ("k8s", "Kubernetes"),
            ("GCP", "Google Cloud"),
            ("cpp", "C++"),
            ("CPP", "C++"),
            ("cplusplus", "C++"),
            ("csharp", "C#"),
            ("C Sharp", "C#"),
            ("dotnet", ".NET"),
            ("Dot Net", ".NET"),
            ("fsharp", "F#"),
        ],
    )
    def test_the_seeded_aliases_resolve(self, alias, expected):
        assert skills.canonical(alias) == expected

    def test_c_cplusplus_csharp_and_fsharp_are_four_skills(self):
        names = {skills.canonical(name) for name in ["C", "C++", "C#", "F#"]}
        assert names == {"C", "C++", "C#", "F#"}
        assert {"C", "C++", "C#", "F#", ".NET", "ASP.NET"} <= set(Skill.objects.values_list("name", flat=True))

    def test_cplusplus_does_not_meet_a_csharp_requirement_or_the_reverse(self):
        assert skills.skill_overlap(["C++"], ["C#"]) == ([], ["C++"])
        assert skills.skill_overlap(["C#"], ["C++"]) == ([], ["C#"])
        assert skills.skill_overlap(["C"], ["C++"]) == ([], ["C"])
        assert skills.skill_overlap(["F#"], ["F"]) == ([], ["F#"])
        assert skills.skill_overlap([".NET"], ["NET"]) == ([], [".NET"])

    @pytest.mark.parametrize(
        "skill, implied",
        [
            ("Django", "Python"),
            ("Django REST Framework", "Django"),
            ("Flask", "Python"),
            ("React", "JavaScript"),
            ("Next.js", "React"),
            ("TypeScript", "JavaScript"),
            ("pandas", "Python"),
            ("PyTorch", "Python"),
            ("Spring Boot", "Java"),
            ("ASP.NET", ".NET"),
        ],
    )
    def test_the_seeded_implications_hold(self, skill, implied):
        assert implied in skills.expand([skill])


@pytest.mark.django_db
class TestCanonical:
    def test_an_alias_resolves_to_its_skill_whatever_the_spelling(self, empty_graph):
        make_skill("PostgreSQL", aliases=["Postgres"])

        assert skills.canonical("postgres") == "PostgreSQL"
        assert skills.canonical("  POSTGRES ") == "PostgreSQL"
        assert skills.canonical("postgresql") == "PostgreSQL"

    def test_an_unknown_skill_is_returned_as_written(self, empty_graph):
        assert skills.canonical("  Elixir ") == "Elixir"

    def test_a_blank_name_has_no_canonical_form(self, empty_graph):
        assert skills.canonical("  ") == ""


@pytest.mark.django_db
class TestExpand:
    def test_implications_are_followed_transitively(self, empty_graph):
        make_skill("Python")
        make_skill("Django", implies=["Python"])
        make_skill("Django REST Framework", aliases=["DRF"], implies=["Django"])

        assert skills.expand(["DRF"]) == {"Django REST Framework", "Django", "Python"}

    def test_a_cycle_does_not_loop_forever(self, empty_graph):
        a = make_skill("A Skill")
        b = make_skill("B Skill", implies=["A Skill"])
        a.implies.add(b)

        assert skills.expand(["A Skill"]) == {"A Skill", "B Skill"}

    def test_a_self_implication_is_harmless(self, empty_graph):
        a = make_skill("Loop")
        a.implies.add(a)

        assert skills.expand(["Loop"]) == {"Loop"}

    def test_unknown_skills_pass_through_by_name(self, empty_graph):
        assert skills.expand(["Elixir", "", "elixir"]) == {"Elixir"}


@pytest.mark.django_db
class TestOverlap:
    def test_a_required_skill_is_matched_through_an_alias(self, empty_graph):
        make_skill("PostgreSQL", aliases=["Postgres"])

        matched, missing = skills.skill_overlap(["PostgreSQL"], ["Postgres"])

        assert matched == ["PostgreSQL"]
        assert missing == []

    def test_a_required_skill_is_matched_through_an_implication(self, empty_graph):
        make_skill("Python")
        make_skill("Django", implies=["Python"])

        matched, missing = skills.skill_overlap(["Python", "Docker"], ["Django"])

        assert matched == ["Python"]
        assert missing == ["Docker"]

    def test_an_implication_does_not_run_backwards(self, empty_graph):
        make_skill("Python")
        make_skill("Django", implies=["Python"])

        assert skills.skill_overlap(["Django"], ["Python"]) == ([], ["Django"])

    def test_duplicate_requirements_are_counted_once(self, empty_graph):
        make_skill("PostgreSQL", aliases=["Postgres"])

        assert skills.skill_overlap(["Postgres", "PostgreSQL"], []) == ([], ["PostgreSQL"])

    def test_with_an_empty_table_matching_falls_back_to_the_slug(self, empty_graph):
        matched, missing = skills.skill_overlap(["Node.js", "Go"], ["node js"])

        assert matched == ["Node.js"]
        assert missing == ["Go"]


@pytest.mark.django_db
class TestCache:
    def test_the_graph_is_loaded_once_per_process(self, empty_graph, django_assert_num_queries):
        make_skill("PostgreSQL", aliases=["Postgres"])
        skills.canonical("Postgres")

        with django_assert_num_queries(0):
            skills.canonical("Postgres")
            skills.expand(["Postgres"])

    def test_adding_an_alias_invalidates_the_cache(self, empty_graph):
        skill = make_skill("PostgreSQL")
        assert skills.canonical("Postgres") == "Postgres"

        SkillAlias.objects.create(skill=skill, name="Postgres")

        assert skills.canonical("Postgres") == "PostgreSQL"

    def test_adding_an_implication_invalidates_the_cache(self, empty_graph):
        make_skill("Python")
        django = make_skill("Django")
        assert skills.expand(["Django"]) == {"Django"}

        django.implies.add(Skill.objects.get(name="Python"))

        assert skills.expand(["Django"]) == {"Django", "Python"}

    def test_deleting_a_skill_invalidates_the_cache(self, empty_graph):
        make_skill("PostgreSQL", aliases=["Postgres"])
        assert skills.canonical("Postgres") == "PostgreSQL"

        Skill.objects.get(name="PostgreSQL").delete()

        assert skills.canonical("Postgres") == "Postgres"

    def test_renaming_a_skill_invalidates_the_cache(self, empty_graph):
        skill = make_skill("Postgresql")
        assert skills.canonical("postgresql") == "Postgresql"

        skill.name = "PostgreSQL"
        skill.save()

        assert skills.canonical("postgresql") == "PostgreSQL"


@pytest.mark.django_db
class TestModels:
    def test_a_skill_is_slugged_on_save(self, empty_graph):
        assert make_skill("Node.js").slug == "nodejs"

    def test_an_alias_cannot_shadow_another_skill(self, empty_graph):
        from django.core.exceptions import ValidationError

        make_skill("Java")
        script = make_skill("JavaScript")

        with pytest.raises(ValidationError):
            SkillAlias(skill=script, name="java").full_clean()


def _embedder():
    return Embedder(FakeLLMClient())


@pytest.mark.django_db
class TestAliasSuggestions:
    def test_a_near_neighbour_above_the_threshold_becomes_a_pending_suggestion(self, empty_graph):
        make_skill("Machine Learning")

        created = skills.suggest_aliases(["machine learning models"], _embedder(), threshold=0.5)

        assert [(s.alias, s.skill.name, s.status) for s in created] == [
            ("machine learning models", "Machine Learning", "pending")
        ]
        assert created[0].similarity >= 0.5

    def test_a_suggestion_is_never_merged_automatically(self, empty_graph):
        make_skill("Machine Learning")

        skills.suggest_aliases(["machine learning models"], _embedder(), threshold=0.5)

        assert not SkillAlias.objects.exists()
        assert skills.canonical("machine learning models") == "machine learning models"

    def test_nothing_is_suggested_below_the_threshold(self, empty_graph):
        make_skill("Machine Learning")

        assert skills.suggest_aliases(["Woodworking"], _embedder(), threshold=0.5) == []
        assert not SkillAliasSuggestion.objects.exists()

    def test_known_names_and_earlier_suggestions_are_not_suggested_again(self, empty_graph):
        make_skill("Machine Learning", aliases=["ML"])
        skills.suggest_aliases(["machine learning models"], _embedder(), threshold=0.5)
        SkillAliasSuggestion.objects.update(status=SkillAliasSuggestion.Status.REJECTED)

        again = skills.suggest_aliases(
            ["Machine Learning", "ml", "Machine learning models"], _embedder(), threshold=0.5
        )

        assert again == []
        assert SkillAliasSuggestion.objects.count() == 1

    def test_an_unreachable_embedder_suggests_nothing(self, empty_graph):
        make_skill("Machine Learning")

        down = Embedder(FakeLLMClient(down=True))

        assert skills.suggest_aliases(["machine learning models"], down, threshold=0.5) == []

    def test_the_threshold_defaults_to_the_setting(self, empty_graph, settings):
        make_skill("Machine Learning")
        settings.SKILL_GRAPH = {**settings.SKILL_GRAPH, "ALIAS_SUGGESTION_THRESHOLD": 0.99}

        assert skills.suggest_aliases(["machine learning models"], _embedder()) == []

    def test_approving_a_suggestion_creates_the_alias(self, empty_graph):
        make_skill("Machine Learning")
        [suggestion] = skills.suggest_aliases(["ML models"], _embedder(), threshold=0.0)

        suggestion.approve()

        suggestion.refresh_from_db()
        assert suggestion.status == "approved"
        assert suggestion.reviewed_at is not None
        assert skills.canonical("ML models") == "Machine Learning"

    def test_the_admin_approve_action_creates_the_alias(self, empty_graph, rf, admin_user):
        make_skill("Machine Learning")
        skills.suggest_aliases(["ML models"], _embedder(), threshold=0.0)
        model_admin = SkillAliasSuggestionAdmin(SkillAliasSuggestion, AdminSite())
        request = rf.post("/")
        request.user = admin_user
        model_admin.message_user = lambda *args, **kwargs: None

        model_admin.approve_selected(request, SkillAliasSuggestion.objects.all())

        assert SkillAlias.objects.filter(name="ML models", skill__name="Machine Learning").exists()

    def test_the_admin_reject_action_creates_no_alias(self, empty_graph, rf, admin_user):
        make_skill("Machine Learning")
        skills.suggest_aliases(["ML models"], _embedder(), threshold=0.0)
        model_admin = SkillAliasSuggestionAdmin(SkillAliasSuggestion, AdminSite())
        request = rf.post("/")
        request.user = admin_user
        model_admin.message_user = lambda *args, **kwargs: None

        model_admin.reject_selected(request, SkillAliasSuggestion.objects.all())

        assert SkillAliasSuggestion.objects.get().status == "rejected"
        assert not SkillAlias.objects.exists()

    def test_saving_a_suggestion_as_approved_in_the_admin_form_creates_the_alias(
        self, empty_graph, rf, admin_user
    ):
        make_skill("Machine Learning")
        [suggestion] = skills.suggest_aliases(["ML models"], _embedder(), threshold=0.0)
        model_admin = SkillAliasSuggestionAdmin(SkillAliasSuggestion, AdminSite())
        request = rf.post("/")
        request.user = admin_user

        suggestion.status = SkillAliasSuggestion.Status.APPROVED
        model_admin.save_model(request, suggestion, form=None, change=True)

        assert SkillAlias.objects.filter(name="ML models").exists()

    def test_approving_an_alias_another_skill_already_owns_fails_and_stays_pending(self, empty_graph):
        """V2: it used to report success and hand back the other skill's alias."""
        from django.core.exceptions import ValidationError

        make_skill("PostgreSQL", aliases=["Postgres"])
        python = make_skill("Python")
        suggestion = SkillAliasSuggestion.objects.create(alias="Postgres", skill=python, similarity=0.9)

        with pytest.raises(ValidationError, match="PostgreSQL"):
            suggestion.approve()

        suggestion.refresh_from_db()
        assert suggestion.status == "pending"
        assert suggestion.reviewed_at is None
        assert skills.canonical("Postgres") == "PostgreSQL"

    def test_approving_another_skills_own_name_fails(self, empty_graph):
        from django.core.exceptions import ValidationError

        make_skill("Java")
        script = make_skill("JavaScript")
        suggestion = SkillAliasSuggestion.objects.create(alias="java", skill=script, similarity=0.9)

        with pytest.raises(ValidationError, match="Java"):
            suggestion.approve()
        assert not SkillAlias.objects.exists()

    def test_approving_an_alias_the_same_skill_already_has_succeeds(self, empty_graph):
        postgres = make_skill("PostgreSQL", aliases=["Postgres"])
        suggestion = SkillAliasSuggestion.objects.create(alias="postgres", skill=postgres, similarity=0.9)

        alias = suggestion.approve()

        assert alias.skill == postgres
        assert SkillAlias.objects.count() == 1
        suggestion.refresh_from_db()
        assert suggestion.status == "approved"

    def test_the_admin_action_reports_a_conflict_and_approves_the_rest(self, empty_graph, rf, admin_user):
        make_skill("PostgreSQL", aliases=["Postgres"])
        python = make_skill("Python")
        clash = SkillAliasSuggestion.objects.create(alias="Postgres", skill=python, similarity=0.9)
        fine = SkillAliasSuggestion.objects.create(alias="Py3", skill=python, similarity=0.9)
        model_admin = SkillAliasSuggestionAdmin(SkillAliasSuggestion, AdminSite())
        request = rf.post("/")
        request.user = admin_user
        messages = []
        model_admin.message_user = lambda request, message, *args, **kwargs: messages.append(message)

        model_admin.approve_selected(request, SkillAliasSuggestion.objects.all())

        clash.refresh_from_db()
        fine.refresh_from_db()
        assert (clash.status, fine.status) == ("pending", "approved")
        assert any("Postgres" in message and "PostgreSQL" in message for message in messages)
        assert any("Approved 1" in message for message in messages)

    def test_saving_a_conflicting_suggestion_as_approved_in_the_admin_form_leaves_it_pending(
        self, empty_graph, rf, admin_user
    ):
        make_skill("PostgreSQL", aliases=["Postgres"])
        python = make_skill("Python")
        suggestion = SkillAliasSuggestion.objects.create(alias="Postgres", skill=python, similarity=0.9)
        model_admin = SkillAliasSuggestionAdmin(SkillAliasSuggestion, AdminSite())
        request = rf.post("/")
        request.user = admin_user
        messages = []
        model_admin.message_user = lambda request, message, *args, **kwargs: messages.append(message)

        suggestion.status = SkillAliasSuggestion.Status.APPROVED
        model_admin.save_model(request, suggestion, form=None, change=True)

        assert SkillAliasSuggestion.objects.get(pk=suggestion.pk).status == "pending"
        assert messages and "PostgreSQL" in messages[0]

    def test_skill_models_are_registered_in_the_admin(self):
        from django.contrib import admin

        for model in (Skill, SkillAlias, SkillAliasSuggestion):
            assert admin.site.is_registered(model)


RESLUG_MIGRATION = ("matching", "0005_reslug_skills_seed_c_family")


def _reslug_migration():
    import importlib

    return importlib.import_module(f"{RESLUG_MIGRATION[0]}.migrations.{RESLUG_MIGRATION[1]}")


def _historical_apps():
    """The models as the migration sees them: no custom `save()`, no signals."""
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    return MigrationExecutor(connection).loader.project_state(RESLUG_MIGRATION).apps


def _run_reslug_migration():
    migration, apps = _reslug_migration(), _historical_apps()
    migration.reslug(apps, None)
    migration.seed(apps, None)


def _run_reslug_only():
    _reslug_migration().reslug(_historical_apps(), None)


def _force_slug(model, pk, slug):
    """Write an old-rule slug past `save()`, as rows written before V1 hold."""
    model.objects.filter(pk=pk).update(slug=slug)


@pytest.mark.django_db
class TestReslugMigration:
    def test_old_slugs_are_rewritten_with_the_new_rule(self, empty_graph):
        csharp = Skill.objects.create(name="C#")
        _force_slug(Skill, csharp.pk, "c")
        dotnet = Skill.objects.create(name=".NET")
        _force_slug(Skill, dotnet.pk, "net")
        alias = SkillAlias.objects.create(skill=csharp, name="C#.")
        _force_slug(SkillAlias, alias.pk, "c")
        suggestion = SkillAliasSuggestion.objects.create(alias="C #", skill=csharp, similarity=0.9)
        _force_slug(SkillAliasSuggestion, suggestion.pk, "c")

        _run_reslug_migration()

        assert Skill.objects.get(pk=csharp.pk).slug == "csharp"
        assert Skill.objects.get(pk=dotnet.pk).slug == "dotnet"
        assert SkillAlias.objects.get(pk=alias.pk).slug == "csharp"
        assert SkillAliasSuggestion.objects.get(pk=suggestion.pk).slug == "csharp"

    def test_the_c_family_is_seeded_around_existing_rows(self, empty_graph):
        csharp = Skill.objects.create(name="C#")
        _force_slug(Skill, csharp.pk, "c")

        _run_reslug_migration()
        skills.reset_skill_graph()

        assert Skill.objects.get(slug="csharp").pk == csharp.pk
        assert skills.canonical("C") == "C"
        assert skills.canonical("cpp") == "C++"
        assert ".NET" in skills.expand(["ASP.NET"])

    def test_two_skills_that_now_share_a_slug_are_merged_into_the_one_already_holding_it(self, empty_graph):
        moved = make_skill("C#", aliases=["Sea Sharp"])
        _force_slug(Skill, moved.pk, "c")
        holder = make_skill("Csharp")
        SkillAliasSuggestion.objects.create(alias="C-Sharp", skill=moved, similarity=0.9)
        SkillAliasSuggestion.objects.create(alias="C Sharp", skill=holder, similarity=0.9)
        SkillAliasSuggestion.objects.create(alias="Sharp C", skill=moved, similarity=0.9)
        target = make_skill("Programming")
        moved.implies.add(target)
        user = make_skill("Unity")
        user.implies.add(moved)

        _run_reslug_only()

        assert not Skill.objects.filter(pk=moved.pk).exists()
        holder.refresh_from_db()
        assert holder.slug == "csharp"
        assert list(holder.aliases.values_list("name", flat=True)) == ["Sea Sharp"]
        assert list(holder.implies.all()) == [target]
        assert list(Skill.objects.get(pk=user.pk).implies.all()) == [holder]
        assert sorted(holder.alias_suggestions.values_list("slug", flat=True)) == ["csharp", "sharpc"]

    def test_two_aliases_that_now_share_a_slug_keep_the_one_already_holding_it(self, empty_graph):
        old = SkillAlias.objects.create(skill=make_skill("Cpp Lang"), name="C++")
        _force_slug(SkillAlias, old.pk, "c")
        holder = SkillAlias.objects.create(skill=make_skill("Systems"), name="cplusplus")

        _run_reslug_only()

        assert list(SkillAlias.objects.values_list("pk", "slug")) == [(holder.pk, "cplusplus")]

    def test_running_it_twice_changes_nothing_more(self, empty_graph):
        _run_reslug_migration()
        before = (
            sorted(Skill.objects.values_list("slug", flat=True)),
            sorted(SkillAlias.objects.values_list("slug", flat=True)),
        )

        _run_reslug_migration()

        assert before == (
            sorted(Skill.objects.values_list("slug", flat=True)),
            sorted(SkillAlias.objects.values_list("slug", flat=True)),
        )
        assert Skill.objects.filter(name="C++").count() == 1
