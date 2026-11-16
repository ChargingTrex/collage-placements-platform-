import { useEffect, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import { ApiError } from '@/api/client'
import { authApi, type DemoPersona } from '@/api/auth'
import { landingPathFor, useAuth } from '@/auth/AuthContext'
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
  const [personas, setPersonas] = useState<DemoPersona[]>([])
  const [demoBusy, setDemoBusy] = useState<string | null>(null)

  // Only a local demo server answers this; anywhere else it is a 404 and the
  // page stays exactly as it was, password only.
  useEffect(() => {
    let cancelled = false
    authApi
      .demoPersonas()
      .then((result) => !cancelled && setPersonas(result.personas ?? []))
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  async function handleDemoLogin(persona: DemoPersona) {
    setError(null)
    setDemoBusy(persona.key)
    try {
      landAfterLogin(await authApi.demoLogin(persona.key))
    } catch (caught) {
      fail(caught)
    } finally {
      setDemoBusy(null)
    }
  }

  function fail(caught: unknown) {
    setError(caught instanceof ApiError ? caught : new ApiError(0, 'Something went wrong.'))
  }

  function landAfterLogin(result: Parameters<typeof signIn>[0]) {
    const user = signIn(result)
    navigate(landingPathFor(user, from), { replace: true })
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

      {personas.length ? (
        <section aria-labelledby="demo-personas" className="mt-6 border-t border-ink-100 pt-5">
          <h2 id="demo-personas" className="text-sm font-medium text-ink-800">
            Demo sign-in
          </h2>
          <p className="mt-1 text-xs text-ink-400">
            Local demo only: one click signs in as a seeded account. Off on the public link.
          </p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {personas.map((persona) => (
              <Button
                key={persona.key}
                type="button"
                variant="secondary"
                size="sm"
                loading={demoBusy === persona.key}
                disabled={demoBusy !== null && demoBusy !== persona.key}
                onClick={() => void handleDemoLogin(persona)}
                className="flex-col items-start! gap-0.5! text-left"
                title={persona.description}
              >
                <span>Sign in as {persona.label}</span>
                <span className="font-mono text-xs font-normal text-ink-400">
                  {persona.identifier}
                </span>
              </Button>
            ))}
          </div>
        </section>
      ) : null}
    </AuthLayout>
  )
}
