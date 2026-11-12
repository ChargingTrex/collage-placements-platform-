import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { ApiError } from '@/api/client'
import { authApi } from '@/api/auth'
import { AuthLayout } from '@/components/AppShell'
import { Alert, Button, Field } from '@/components/ui'

export default function SignupPage() {
  const navigate = useNavigate()
  const [prn, setPrn] = useState('')
  const [email, setEmail] = useState('')
  const [error, setError] = useState<ApiError | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const issued = await authApi.signup(prn, email)
      navigate('/verify', {
        state: { identifier: issued.prn ?? prn, email: issued.email ?? email, debugOtp: issued.debug_otp },
      })
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, 'Something went wrong.'))
    } finally {
      setSubmitting(false)
    }
  }

  // A rejected identity is not a form error -- say what to do about it.
  const rejected = error?.status === 403

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Your PRN and college email are checked against the placement cell's roster."
      footer={
        <>
          Already verified? <Link className="text-brand-600 hover:underline" to="/login">Sign in</Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        {rejected ? (
          <Alert tone="error" title="We couldn't match you to the roster">
            <p>{error.message}</p>
            <p className="mt-2 text-xs">
              This attempt has been sent to the placement cell for review.
            </p>
          </Alert>
        ) : error && !Object.keys(error.fieldErrors).length ? (
          <Alert tone="error">{error.message}</Alert>
        ) : null}

        <Field
          label="PRN"
          name="prn"
          value={prn}
          onChange={(event) => setPrn(event.target.value)}
          placeholder="220200901"
          autoComplete="username"
          required
          errors={error?.fieldErrors.prn}
          hint="Permanent Registration Number, as printed on your ID card."
        />
        <Field
          label="College email"
          name="email"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@college.edu"
          autoComplete="email"
          required
          errors={error?.fieldErrors.email}
        />

        <Button type="submit" loading={submitting} className="w-full">
          Send verification code
        </Button>
      </form>
    </AuthLayout>
  )
}
