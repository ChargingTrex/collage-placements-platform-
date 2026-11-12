import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import { ApiError } from '@/api/client'
import { authApi } from '@/api/auth'
import { homePathFor, useAuth } from '@/auth/AuthContext'
import { AuthLayout } from '@/components/AppShell'
import { Alert, Button, Field } from '@/components/ui'

type Method = 'password' | 'code'

export default function LoginPage() {
  const navigate = useNavigate()
  const { signIn } = useAuth()
  const from = (useLocation().state as { from?: string } | null)?.from

  const [method, setMethod] = useState<Method>('password')
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [codeSent, setCodeSent] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [submitting, setSubmitting] = useState(false)

  function fail(caught: unknown) {
    setError(caught instanceof ApiError ? caught : new ApiError(0, 'Something went wrong.'))
  }

  function landAfterLogin(result: Parameters<typeof signIn>[0]) {
    const user = signIn(result)
    navigate(from && from !== '/login' ? from : homePathFor(user), { replace: true })
  }

  async function handlePasswordLogin(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      landAfterLogin(await authApi.login(identifier, password))
    } catch (caught) {
      fail(caught)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRequestCode() {
    setError(null)
    setSubmitting(true)
    try {
      const issued = await authApi.requestOtp(identifier)
      setCodeSent(true)
      setNotice(issued.detail)
      if (issued.debug_otp) setCode(issued.debug_otp)
    } catch (caught) {
      fail(caught)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleCodeLogin(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      landAfterLogin(await authApi.otpLogin(identifier, code))
    } catch (caught) {
      fail(caught)
    } finally {
      setSubmitting(false)
    }
  }

  const needsVerification = error?.status === 403 && 'needs_verification' in (error.fieldErrors ?? {})

  return (
    <AuthLayout
      title="Sign in"
      subtitle="Students use their PRN or college email. Admins and recruiters use their email."
      footer={
        <>
          New student? <Link className="text-brand-600 hover:underline" to="/signup">Create an account</Link>
        </>
      }
    >
      <div
        role="tablist"
        aria-label="Sign-in method"
        className="mb-5 grid grid-cols-2 gap-1 rounded-lg bg-ink-100 p-1"
      >
        {(['password', 'code'] as const).map((value) => (
          <button
            key={value}
            role="tab"
            type="button"
            aria-selected={method === value}
            onClick={() => {
              setMethod(value)
              setError(null)
              setNotice(null)
            }}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
              method === value ? 'bg-white text-ink-900 shadow-sm' : 'text-ink-600 hover:text-ink-800'
            }`}
          >
            {value === 'password' ? 'Password' : 'Email code'}
          </button>
        ))}
      </div>

      {error ? (
        <div className="mb-4">
          <Alert tone="error">
            {error.message}
            {needsVerification || error.status === 403 ? (
              <>
                {' '}
                <Link className="underline" to="/signup">
                  Finish verifying
                </Link>
                .
              </>
            ) : null}
          </Alert>
        </div>
      ) : null}

      {notice && !error ? (
        <div className="mb-4">
          <Alert tone="success">{notice}</Alert>
        </div>
      ) : null}

      {method === 'password' ? (
        <form onSubmit={handlePasswordLogin} className="space-y-4" noValidate>
          <Field
            label="PRN or email"
            name="identifier"
            value={identifier}
            onChange={(event) => setIdentifier(event.target.value)}
            autoComplete="username"
            required
            errors={error?.fieldErrors.identifier}
          />
          <Field
            label="Password"
            name="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
            errors={error?.fieldErrors.password}
          />
          <Button type="submit" loading={submitting} className="w-full">
            Sign in
          </Button>
        </form>
      ) : (
        <form onSubmit={handleCodeLogin} className="space-y-4" noValidate>
          <Field
            label="PRN or email"
            name="identifier"
            value={identifier}
            onChange={(event) => setIdentifier(event.target.value)}
            autoComplete="username"
            required
            errors={error?.fieldErrors.identifier}
          />

          {codeSent ? (
            <Field
              label="Code from your email"
              name="code"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              inputMode="numeric"
              autoComplete="one-time-code"
              required
            />
          ) : null}

          {codeSent ? (
            <Button type="submit" loading={submitting} className="w-full">
              Sign in
            </Button>
          ) : (
            <Button
              type="button"
              loading={submitting}
              className="w-full"
              disabled={!identifier}
              onClick={handleRequestCode}
            >
              Email me a code
            </Button>
          )}
        </form>
      )}
    </AuthLayout>
  )
}
