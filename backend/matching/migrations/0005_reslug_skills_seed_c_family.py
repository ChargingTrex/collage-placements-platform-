"""
Re-slug the skill graph and seed C, C++, C#, .NET and F# (finding V1).

The old `slugify_skill` dropped "+", "#" and a leading dot, so C, C++ and C#
were one skill and `0003_seed_skills` had to leave all three out. Every
skill, alias and alias suggestion slug is recomputed with the new rule,
frozen below, and then the missing skills are added.

The new rule only splits old slugs, except where two spellings of one skill
now meet ("C#" and "Csharp"). A slug is unique, so the row already holding
it stays: a second skill is merged into it (its aliases, suggestions and
implications move over), a second alias or suggestion is deleted.

Like `0003_seed_skills`, the seed only adds what is missing, so running it
again or after an admin's edits changes nothing. The reverse is a no-op.

Vectors written before this hold the old slugs in their filter metadata.
`manage.py reindex_vectors` refreshes them; it is not run here, because it
may call the embedding service.
"""

import re

from django.db import migrations

#: (canonical name, aliases, implied skills). "cplusplus", "csharp" and
#: "dotnet" need no alias row: they are already the skills' own slugs.
SEED = [
    ("C", [], []),
    ("C++", ["CPP"], []),
    ("C#", [], []),
    ("F#", [], []),
    (".NET", [], []),
    # A framework implies its platform, as Django implies Python. .NET does
    # not imply C#: F# and VB.NET run on it too.
    ("ASP.NET", [], [".NET"]),
]


def _slug(name):
    # Must stay identical to matching.models.slugify_skill as of this migration.
    name = (name or "").strip().lower()
    name = re.sub(r"^\.", "dot", name).replace("+", "plus").replace("#", "sharp")
    return re.sub(r"[^a-z0-9]+", "", name)


def _resolve(rows, key):
    """Split `rows` into (row -> new slug) to keep, and rows that lost a clash."""
    groups = {}
    for row in sorted(rows, key=lambda row: row.pk):
        groups.setdefault(key(row), []).append(row)
    keep, lost = {}, []
    for group_key, group in groups.items():
        slug = group_key[0] if isinstance(group_key, tuple) else group_key
        winner = next((row for row in group if row.slug == slug), group[0])
        keep[winner] = slug
        lost.extend((row, winner) for row in group if row is not winner)
    return keep, lost


def _write(model, keep):
    """Apply new slugs through unique placeholders, so no write clashes midway."""
    changed = [row for row, slug in keep.items() if row.slug != slug]
    for row in changed:
        row.slug = f"~{row.pk}"
    model.objects.bulk_update(changed, ["slug"])
    for row in changed:
        row.slug = keep[row]
    model.objects.bulk_update(changed, ["slug"])


def reslug(apps, schema_editor):
    Skill = apps.get_model("matching", "Skill")
    SkillAlias = apps.get_model("matching", "SkillAlias")
    SkillAliasSuggestion = apps.get_model("matching", "SkillAliasSuggestion")

    keep, lost = _resolve(Skill.objects.all(), lambda row: _slug(row.name))
    for loser, winner in lost:
        SkillAlias.objects.filter(skill=loser).update(skill=winner)
        for pk in SkillAliasSuggestion.objects.filter(skill=loser).values_list("pk", flat=True):
            # A placeholder slug, so the move cannot clash with the winner's
            # own suggestions; the pass below re-slugs and dedupes them.
            SkillAliasSuggestion.objects.filter(pk=pk).update(skill=winner, slug=f"~{pk}")
        others = [loser.pk, winner.pk]
        winner.implies.add(*loser.implies.exclude(pk__in=others))
        for source in loser.implied_by.exclude(pk__in=others):
            source.implies.add(winner)
        loser.delete()
    _write(Skill, keep)

    keep, lost = _resolve(SkillAlias.objects.all(), lambda row: _slug(row.name))
    SkillAlias.objects.filter(pk__in=[row.pk for row, _ in lost]).delete()
    _write(SkillAlias, keep)

    keep, lost = _resolve(
        SkillAliasSuggestion.objects.all(), lambda row: (_slug(row.alias), row.skill_id)
    )
    SkillAliasSuggestion.objects.filter(pk__in=[row.pk for row, _ in lost]).delete()
    _write(SkillAliasSuggestion, keep)


def seed(apps, schema_editor):
    Skill = apps.get_model("matching", "Skill")
    SkillAlias = apps.get_model("matching", "SkillAlias")

    by_name = {}
    for name, aliases, _ in SEED:
        skill, _ = Skill.objects.get_or_create(slug=_slug(name), defaults={"name": name})
        by_name[name] = skill
        for alias in aliases:
            slug = _slug(alias)
            if Skill.objects.filter(slug=slug).exists():
                continue
            SkillAlias.objects.get_or_create(slug=slug, defaults={"skill": skill, "name": alias})

    for name, _, implied in SEED:
        by_name[name].implies.add(*(by_name[target] for target in implied))


def forget_cached_graph(apps, schema_editor):
    """Historical models fire no signal the live cache listens to."""
    try:
        from matching.skills import reset_skill_graph
    except ImportError:  # the module moved on; nothing to forget then
        return
    reset_skill_graph()


class Migration(migrations.Migration):

    dependencies = [
        ("matching", "0004_role_category"),
    ]

    operations = [
        migrations.RunPython(reslug, migrations.RunPython.noop),
        migrations.RunPython(seed, migrations.RunPython.noop),
        migrations.RunPython(forget_cached_graph, migrations.RunPython.noop),
    ]
