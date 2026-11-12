"""
Re-slug profile skills so C, C++ and C# are three skills (finding V1).

The old `slugify_skill` dropped "+", "#" and a leading dot, so "C", "C++"
and "C#" all keyed to "c", and ".NET" to "net". Every stored slug is
recomputed with the new rule, frozen below.

The new rule only splits old slugs, except where two spellings of one skill
now meet ("C++" and "cplusplus" on one profile). One profile cannot hold a
slug twice, so the row already holding it stays and the other, the same
skill entered twice, is deleted.

A profile whose slugs changed has its analysis marked `needs_reindex`: its
vector's filter metadata still holds the old slugs. Run
`manage.py reindex_vectors` (all profiles, since the skill graph changed in
`matching.0005` too) after deploying; this migration does not, because it
may call the embedding service.

The reverse is a no-op: the old slugs merged skills that differ.
"""

import re

from django.db import migrations


def _slug(name):
    # Must stay identical to profiles.models.slugify_skill as of this migration.
    name = (name or "").strip().lower()
    name = re.sub(r"^\.", "dot", name).replace("+", "plus").replace("#", "sharp")
    return re.sub(r"[^a-z0-9]+", "", name)


def reslug(apps, schema_editor):
    ProfileSkill = apps.get_model("profiles", "ProfileSkill")
    ResumeAnalysis = apps.get_model("profiles", "ResumeAnalysis")

    rows = list(ProfileSkill.objects.order_by("pk"))
    groups = {}
    for row in rows:
        groups.setdefault((row.profile_id, _slug(row.name)), []).append(row)

    changed, dropped, touched = [], [], set()
    for (profile_id, slug), group in groups.items():
        keep = next((row for row in group if row.slug == slug), group[0])
        dropped.extend(row.pk for row in group if row is not keep)
        if keep.slug != slug:
            keep.slug = slug
            changed.append(keep)
            touched.add(profile_id)
        if len(group) > 1:
            touched.add(profile_id)

    ProfileSkill.objects.filter(pk__in=dropped).delete()
    # Through a unique placeholder first, so no row briefly takes a slug
    # another row is about to give up.
    final = {row.pk: row.slug for row in changed}
    for row in changed:
        row.slug = f"~{row.pk}"
    ProfileSkill.objects.bulk_update(changed, ["slug"])
    for row in changed:
        row.slug = final[row.pk]
    ProfileSkill.objects.bulk_update(changed, ["slug"])

    ResumeAnalysis.objects.filter(profile_id__in=touched).update(needs_reindex=True)


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0003_resume_analysis"),
    ]

    operations = [
        migrations.RunPython(reslug, migrations.RunPython.noop),
    ]
