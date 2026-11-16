import { useState } from 'react'

import { ApiError } from '@/api/client'
import {
  describeApplyRefusal,
  formatSalary,
  opportunitiesApi,
  type FeedRow,
} from '@/api/opportunities'
import { MatchBreakdown, ScoreBar, SkillChips } from '@/components/MatchDisplay'
import { ApplicationStatusBadge } from '@/components/StatusBadges'
import { Alert, Badge, Button, Card } from '@/components/ui'

/** One ranked posting with its score, eligibility flag and Apply. Shared by Jobs and Suggestions. */
export default function JobCard({
  row,
  onApplied,
}: {
  row: FeedRow
  onApplied: (id: string, status: FeedRow['application_status']) => void
}) {
  const [busy, setBusy] = useState(false)
  const [refusal, setRefusal] = useState<string | null>(null)

  async function apply() {
    setBusy(true)
    setRefusal(null)
    try {
      const application = await opportunitiesApi.apply(row.id)
      onApplied(row.id, application.status)
    } catch (caught) {
      if (caught instanceof ApiError) {
        // Apply can be refused for several reasons (D28); each gets its own sentence.
        // A posting that is no longer visible to students answers 404.
        setRefusal(
          caught.status === 404
            ? 'This posting is no longer available.'
            : describeApplyRefusal(caught.reason, caught.message),
        )
      } else setRefusal('Could not apply. Try again.')
    } finally {
      setBusy(false)
    }
  }

  const matchLike = {
    score: row.score,
    components: row.components,
    matched_skills: row.matched_skills,
    missing_skills: row.missing_skills,
    hard_filter_failures: [],
    flagged: false,
    semantic_source: '',
  }

  return (
    <Card className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{row.title}</h2>
          <p className="text-sm text-ink-600">
            {row.company_name ? `${row.company_name} · ` : ''}
            {row.role_type === 'internship' ? 'Internship' : 'Full time'}
            {row.location ? ` · ${row.location}` : ''}
          </p>
          <p className="text-sm text-ink-600">
            {formatSalary(row)} · Deadline {row.deadline}
          </p>
        </div>
        {/* Eligibility is a flag beside the score, never part of it (D28). */}
        <Badge tone={row.eligible ? 'success' : 'warning'}>
          {row.eligible ? 'Eligible' : 'Not eligible'}
        </Badge>
      </div>

      <div className="max-w-xs">
        <ScoreBar score={row.score} size="sm" />
        <p className="mt-1 text-xs text-ink-400">A guide to where you stand, not a prediction.</p>
      </div>

      <SkillChips match={matchLike} />

      <details>
        <summary className="cursor-pointer text-sm text-brand-700">
          How this score is made up
        </summary>
        <div className="mt-2">
          <MatchBreakdown match={matchLike} />
        </div>
      </details>

      {!row.eligible && row.eligibility_reasons.length ? (
        <ul
          className="list-disc space-y-0.5 pl-5 text-sm text-warn-600"
          aria-label="Why you are not eligible"
        >
          {row.eligibility_reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : null}

      {refusal ? <Alert tone="error">{refusal}</Alert> : null}

      <div className="flex items-center gap-3">
        {row.has_applied && row.application_status ? (
          <>
            <span className="text-sm text-ink-600">Your application:</span>
            <ApplicationStatusBadge status={row.application_status} />
          </>
        ) : (
          <Button size="sm" loading={busy} disabled={!row.eligible} onClick={() => void apply()}>
            Apply
          </Button>
        )}
      </div>
    </Card>
  )
}
