"""
Seed the skill graph.

A data migration rather than a `seed_skills` command: `migrate` is the one
step every environment already runs (the backend container runs it on
start), so a fresh clone matches "Postgres" to "PostgreSQL" with no extra
manual step. It only adds what is missing and its reverse is a no-op, so an
admin's later edits in Django admin are never overwritten or deleted.

The data is frozen here on purpose: a migration must give the same result
whenever it runs, whatever the code looks like later.
"""

import re

from django.db import migrations

#: (canonical name, aliases, implied skills). C, C++ and C# are left out:
#: all three slug to "c" (see `slugify_skill`), so the graph cannot tell
#: them apart yet.
SEED = [
    ("Python", [], []),
    ("Java", [], []),
    ("JavaScript", ["JS", "ECMAScript"], []),
    ("TypeScript", ["TS"], ["JavaScript"]),
    ("Go", ["Golang"], []),
    ("SQL", [], []),
    ("PostgreSQL", ["Postgres"], ["SQL"]),
    ("MySQL", [], ["SQL"]),
    ("MongoDB", ["Mongo"], []),
    ("Django", [], ["Python"]),
    ("Django REST Framework", ["DRF"], ["Django"]),
    ("Flask", [], ["Python"]),
    ("FastAPI", [], ["Python"]),
    ("pandas", [], ["Python"]),
    ("NumPy", [], ["Python"]),
    ("Machine Learning", ["ML"], []),
    ("Deep Learning", ["DL"], ["Machine Learning"]),
    ("scikit-learn", ["sklearn"], ["Python", "Machine Learning"]),
    ("PyTorch", [], ["Python", "Deep Learning"]),
    ("TensorFlow", [], ["Python", "Deep Learning"]),
    ("React", ["React.js"], ["JavaScript"]),
    ("Next.js", [], ["React"]),
    ("Node.js", ["Node"], ["JavaScript"]),
    ("Express", ["Express.js"], ["Node.js"]),
    ("Vue.js", ["Vue"], ["JavaScript"]),
    ("Angular", [], ["TypeScript"]),
    ("HTML", ["HTML5"], []),
    ("CSS", ["CSS3"], []),
    ("Spring Boot", [], ["Java"]),
    ("Docker", [], []),
    ("Kubernetes", ["k8s"], []),
    ("AWS", ["Amazon Web Services"], []),
    ("Google Cloud", ["GCP", "Google Cloud Platform"], []),
    ("Microsoft Azure", ["Azure"], []),
    ("Git", [], []),
    ("Linux", [], []),
]


def _slug(name):
    # Must stay identical to matching.models.slugify_skill.
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


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


class Migration(migrations.Migration):

    dependencies = [
        ("matching", "0002_skill_graph"),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
