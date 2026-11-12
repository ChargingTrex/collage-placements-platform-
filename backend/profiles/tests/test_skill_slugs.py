"""
Profile skill slugs keep C, C++ and C# apart (finding V1).

Rows written before the fix hold the old slug, "c" for all three; the data
migration rewrites them and marks the vector for a reindex, since its
filter metadata holds the old slugs.
"""

import importlib

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from profiles.models import ProfileSkill, ResumeAnalysis

MIGRATION = ("profiles", "0004_reslug_skills")
# The state must match the live tables (UUID pks since 0005); the data step is
# still imported from 0004. If you add a later profiles migration, nothing to change.
STATE = ("profiles", "0005_uuid_primary_keys")


def run_migration():
    """Run the data step with the models as the migration sees them."""
    apps = MigrationExecutor(connection).loader.project_state(STATE).apps
    importlib.import_module(f"{MIGRATION[0]}.migrations.{MIGRATION[1]}").reslug(apps, None)


def old_skill(profile, name, slug):
    """A skill row as written under the old rule, past `save()`."""
    skill = ProfileSkill.objects.create(profile=profile, name=name)
    ProfileSkill.objects.filter(pk=skill.pk).update(slug=slug)
    return skill


@pytest.mark.django_db
class TestProfileSkillSlugs:
    def test_cplusplus_and_csharp_on_one_profile_are_two_skills(self, profile):
        ProfileSkill.objects.create(profile=profile, name="C++")
        ProfileSkill.objects.create(profile=profile, name="C#")
        ProfileSkill.objects.create(profile=profile, name="C")

        assert sorted(profile.skills.values_list("slug", flat=True)) == ["c", "cplusplus", "csharp"]


@pytest.mark.django_db
class TestReslugMigration:
    def test_old_slugs_are_rewritten_and_the_vector_marked_for_reindex(self, profile, other_profile):
        cpp = old_skill(profile, "C++", "c")
        dotnet = old_skill(profile, ".NET", "net")
        python = ProfileSkill.objects.create(profile=other_profile, name="Python")
        ResumeAnalysis.objects.create(profile=profile, status="done")
        ResumeAnalysis.objects.create(profile=other_profile, status="done")

        run_migration()

        assert ProfileSkill.objects.get(pk=cpp.pk).slug == "cplusplus"
        assert ProfileSkill.objects.get(pk=dotnet.pk).slug == "dotnet"
        assert ProfileSkill.objects.get(pk=python.pk).slug == "python"
        assert ResumeAnalysis.objects.get(profile=profile).needs_reindex is True
        assert ResumeAnalysis.objects.get(profile=other_profile).needs_reindex is False

    def test_one_skill_entered_twice_keeps_the_row_already_holding_the_slug(self, profile):
        old_skill(profile, "C++", "c")
        holder = ProfileSkill.objects.create(profile=profile, name="cplusplus")
        ResumeAnalysis.objects.create(profile=profile, status="done")

        run_migration()

        assert list(profile.skills.values_list("pk", "slug")) == [(holder.pk, "cplusplus")]
        assert ResumeAnalysis.objects.get(profile=profile).needs_reindex is True

    def test_running_it_twice_changes_nothing_more(self, profile):
        old_skill(profile, "C#", "c")
        run_migration()
        before = list(profile.skills.values_list("pk", "slug"))

        run_migration()

        assert list(profile.skills.values_list("pk", "slug")) == before
