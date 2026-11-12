import { Link } from 'react-router-dom'

import SystemStatus from '@/components/SystemStatus'

const POINTS = [
  {
    title: 'One verified profile',
    body: 'Experience, projects and skills in a structure companies can filter — not a PDF in a shared drive.',
  },
  {
    title: 'Opportunities ranked for you',
    body: 'Postings scored against your profile and resume, with an eligibility flag before you apply.',
  },
  {
    title: 'Certifications that close your gaps',
    body: 'Suggestions drawn from the skills open postings actually ask for.',
  },
]

export default function LandingPage() {
  return (
    <div className="mx-auto max-w-5xl px-6 py-16">
      <p className="text-xs font-semibold tracking-widest text-brand-600 uppercase">
        Placement Cell
      </p>
      <h1 className="mt-2 max-w-2xl text-4xl font-semibold tracking-tight text-balance">
        Everything a placement drive needs, in one place.
      </h1>
      <p className="mt-3 max-w-xl text-ink-600">
        Students sign in with their PRN and college email. Companies browse standardised,
        verified profiles. The placement cell stops chasing spreadsheets.
      </p>

      <div className="mt-8 flex flex-wrap gap-3">
        <Link
          to="/signup"
          className="rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-brand-700"
        >
          Create your student account
        </Link>
        <Link
          to="/login"
          className="rounded-lg bg-white px-5 py-2.5 text-sm font-medium text-ink-800 ring-1 ring-ink-200 transition hover:bg-ink-50"
        >
          Sign in
        </Link>
      </div>

      <div className="mt-14 grid gap-6 sm:grid-cols-3">
        {POINTS.map((point) => (
          <div key={point.title}>
            <h2 className="text-sm font-semibold text-ink-900">{point.title}</h2>
            <p className="mt-1 text-sm text-ink-600">{point.body}</p>
          </div>
        ))}
      </div>

      <div className="mt-14 max-w-sm">
        <SystemStatus />
      </div>
    </div>
  )
}
