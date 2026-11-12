import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'

import { ApiError } from '@/api/client'
import { areaOf, authApi } from '@/api/auth'
import { homePathFor, useAuth } from '@/auth/AuthContext'
import { AuthLayout } from '@/components/AppShell'
import { Alert, Button, Field } from '@/components/ui'

interface VerifyState {
  identifier?: string
  email?: string
  debugOtp?: string
}

export default function VerifyPage() {
  const navigate = useNavigate()
  const { signIn } = useAuth()
  const state = (useLocation().state ?? {}) as VerifyState

  const [code, setCode] = useState(state.debugOtp ?? '')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<ApiError | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Reached directly, with no signup behind it, there is nothing to verify.
  if (!state.identifier) return <Navigate to="/signup" replace />

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const result = await authApi.verify(state.identifier!, code, password)
      const user = signIn(result)
      // A new student starts on the onboarding form; the page sends anyone
      // who already finished it straight on to the dashboard.
      navigate(areaOf(user) === 'student' ? '/student/onboarding' : homePathFor(user), {
        replace: true,
      })
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, 'Something went wrong.'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout
      title="Verify your email"
      subtitle={`We sent a code to ${state.email ?? 'your college email'}. It expires in a few minutes.`}
      footer={
        <>
          Wrong details? <Link className="text-brand-600 hover:underline" to="/signup">Start again</Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        {state.debugOtp ? (
          <Alert tone="info" title="Development mode">
            The backend is running with <code>DEBUG</code> on, so the code is filled in for you.
          </Alert>
        ) : null}

        {error && !Object.keys(error.fieldErrors).length ? (
          <Alert tone="error">{error.message}</Alert>
        ) : null}

        <Field
          label="Verification code"
          name="code"
          value={code}
          onChange={(event) => setCode(event.target.value)}
          inputMode="numeric"
          autoComplete="one-time-code"
          placeholder="123456"
          required
          errors={error?.fieldErrors.code}
        />
        <Field
          label="Choose a password"
          name="password"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="new-password"
          required
          errors={error?.fieldErrors.password}
          hint="At least 8 characters, and not an obvious one."
        />

        <Button type="submit" loading={submitting} className="w-full">
          Verify and continue
        </Button>
      </form>
    </AuthLayout>
  )
}
