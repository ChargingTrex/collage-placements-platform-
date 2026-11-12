import type { MatchComponentName, MatchScore } from '@/api/matching'
import { Badge } from '@/components/ui'

const COMPONENT_LABELS: Record<MatchComponentName, { label: string; hint: string }> = {
  semantic: { label: 'Semantic', hint: 'How closely the profile reads like the job description' },
  skills: { label: 'Skills', hint: 'Required skills held, counting aliases and related skills' },
  experience: { label: 'Experience', hint: 'Years held against the minimum asked for' },
  education: { label: 'Education', hint: 'Whether a held education level is accepted' },
}

const COMPONENT_ORDER: MatchComponentName[] = ['semantic', 'skills', 'experience', 'education']

function percent(value: number): number {
  return Math.round(Math.min(1, Math.max(0, value)) * 100)
}

/**
 * The 0-100 match as a bar with its number in words beside it, so the value
 * never depends on seeing the bar.
 */
export function ScoreBar({ score, size = 'md' }: { score: number; size?: 'sm' | 'md' }) {
  const clamped = Math.round(Math.min(100, Math.max(0, score)))
  const text = `Match ${clamped} of 100`
  return (
    <div className="space-y-1">
      <p className={size === 'md' ? 'text-sm font-medium text-ink-800' : 'text-xs font-medium text-ink-600'}>
        {text}
      </p>
      <div
        role="meter"
        aria-label="Match"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={clamped}
        aria-valuetext={text}
        className={`overflow-hidden rounded-full bg-ink-100 ${size === 'md' ? 'h-2.5' : 'h-1.5'}`}
      >
        <div className="h-full rounded-full bg-brand-600" style={{ width: `${clamped}%` }} />
      </div>
    </div>
  )
}

/** Matched and missing skills as labelled lists, not colour alone. */
export function SkillChips({ match }: { match: MatchScore }) {
  if (!match.matched_skills.length && !match.missing_skills.length) {
    return <p className="text-sm text-ink-400">The job description names no skill we recognise.</p>
  }
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div>
        <p className="text-xs font-medium tracking-wide text-ink-600 uppercase">Matched skills</p>
        {match.matched_skills.length ? (
          <ul className="mt-1.5 flex flex-wrap gap-1.5" aria-label="Matched skills">
            {match.matched_skills.map((skill) => (
              <li key={skill}>
                <Badge tone="success">{skill}</Badge>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1.5 text-sm text-ink-400">None</p>
        )}
      </div>
      <div>
        <p className="text-xs font-medium tracking-wide text-ink-600 uppercase">Missing skills</p>
        {match.missing_skills.length ? (
          <ul className="mt-1.5 flex flex-wrap gap-1.5" aria-label="Missing skills">
            {match.missing_skills.map((skill) => (
              <li key={skill}>
                <Badge tone="warning">{skill}</Badge>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1.5 text-sm text-ink-400">None</p>
        )}
      </div>
    </div>
  )
}

/**
 * Each part of the match with its weight. A single number looks more exact
 * than it is, so wherever the score is shown this can be too.
 */
export function MatchBreakdown({ match }: { match: MatchScore }) {
  return (
    <div className="space-y-3">
      <table className="w-full text-sm">
        <caption className="sr-only">Match breakdown</caption>
        <thead>
          <tr className="text-left text-xs text-ink-400">
            <th scope="col" className="pb-1 font-medium">
              Part
            </th>
            <th scope="col" className="pb-1 text-right font-medium">
              Score
            </th>
            <th scope="col" className="pb-1 text-right font-medium">
              Weight
            </th>
          </tr>
        </thead>
        <tbody>
          {COMPONENT_ORDER.map((name) => {
            const part = match.components[name]
            if (!part) return null
            const counted = part.weight > 0
            return (
              <tr key={name} className="border-t border-ink-100">
                <th scope="row" className="py-1.5 text-left font-normal">
                  <span className="block font-medium text-ink-800">{COMPONENT_LABELS[name].label}</span>
                  <span className="block text-xs text-ink-400">{COMPONENT_LABELS[name].hint}</span>
                </th>
                <td className="py-1.5 text-right tabular-nums">
                  {counted ? `${percent(part.score)}%` : '—'}
                </td>
                <td className="py-1.5 text-right tabular-nums">
                  {counted ? `${percent(part.weight)}%` : 'not counted'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      {match.hard_filter_failures.length ? (
        <div>
          <p className="text-xs font-medium tracking-wide text-ink-600 uppercase">
            Below what the job asks for
          </p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-warn-600">
            {match.hard_filter_failures.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
