# A3 — Certifications

Read [`CONTEXT.md`](../CONTEXT.md) first. Your phase is **C**, after Checkpoint B.

## You own

`certifications/` (empty scaffolding today). Build to `agents.md` Phase 5.

## Notes

- Suggestions **recompute** as a student's skills or the set of open
  opportunities change. A stale suggestion list is worse than none.
- Every suggestion carries a reason string naming the skill and the count —
  "3 open opportunities in your department ask for AWS".
- Proof uploads go through `core/storage.py`, the same boundary as resumes.
  Request the new upload type from A1; do not add it yourself.
- Skill matching is on a **slug**, not the display name — `slugify_skill` in
  `profiles/models.py` collapses "Node.js", "node js" and "NodeJS". Use it.
- There is no skill catalog today; skills are free text per profile. If you
  need one, raise it — it affects `ProfileSkill` and therefore A5.
