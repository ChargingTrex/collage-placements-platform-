import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react'

function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(' ')
}

/* -------------------------------------------------------------- Button --- */

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md'
  loading?: boolean
}

const BUTTON_VARIANTS = {
  primary: 'bg-brand-600 text-white hover:bg-brand-700 disabled:bg-brand-600/50',
  secondary: 'bg-white text-ink-800 ring-1 ring-ink-200 hover:bg-ink-50',
  ghost: 'text-ink-600 hover:bg-ink-100',
  danger: 'bg-bad-600 text-white hover:bg-bad-600/90',
} as const

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled,
  children,
  className,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={cx(
        'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition',
        'focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none',
        'disabled:cursor-not-allowed disabled:opacity-60',
        size === 'sm' ? 'px-3 py-1.5 text-sm' : 'px-4 py-2.5 text-sm',
        BUTTON_VARIANTS[variant],
        className,
      )}
    >
      {loading ? <Spinner /> : null}
      {children}
    </button>
  )
}

function Spinner() {
  return (
    <span
      aria-hidden
      className="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
    />
  )
}

/* --------------------------------------------------------------- Field --- */

type FieldProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string
  hint?: string
  errors?: string[]
}

export function Field({ label, hint, errors, id, className, ...rest }: FieldProps) {
  const fieldId = id ?? rest.name ?? label.toLowerCase().replace(/\s+/g, '-')
  const describedBy = errors?.length ? `${fieldId}-error` : hint ? `${fieldId}-hint` : undefined

  return (
    <div className="space-y-1.5">
      <label htmlFor={fieldId} className="block text-sm font-medium text-ink-800">
        {label}
      </label>
      <input
        {...rest}
        id={fieldId}
        aria-describedby={describedBy}
        aria-invalid={errors?.length ? true : undefined}
        className={cx(
          'w-full rounded-lg border bg-white px-3 py-2.5 text-sm',
          'placeholder:text-ink-400 focus:ring-2 focus:ring-brand-500/30 focus:outline-none',
          errors?.length ? 'border-bad-600 focus:border-bad-600' : 'border-ink-200 focus:border-brand-500',
          className,
        )}
      />
      {errors?.length ? (
        <p id={`${fieldId}-error`} className="text-sm text-bad-600">
          {errors.join(' ')}
        </p>
      ) : hint ? (
        <p id={`${fieldId}-hint`} className="text-xs text-ink-400">
          {hint}
        </p>
      ) : null}
    </div>
  )
}

type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & { label: string }

export function Select({ label, id, children, className, ...rest }: SelectProps) {
  const fieldId = id ?? rest.name ?? label.toLowerCase().replace(/\s+/g, '-')
  return (
    <div className="space-y-1.5">
      <label htmlFor={fieldId} className="block text-sm font-medium text-ink-800">
        {label}
      </label>
      <select
        {...rest}
        id={fieldId}
        className={cx(
          'w-full rounded-lg border border-ink-200 bg-white px-3 py-2.5 text-sm',
          'focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 focus:outline-none',
          className,
        )}
      >
        {children}
      </select>
    </div>
  )
}

/* --------------------------------------------------------------- Alert --- */

const ALERT_TONES = {
  info: 'border-brand-500/25 bg-brand-50 text-brand-700',
  success: 'border-ok-600/25 bg-ok-50 text-ok-600',
  warning: 'border-warn-600/25 bg-warn-50 text-warn-600',
  error: 'border-bad-600/25 bg-bad-50 text-bad-600',
} as const

export function Alert({
  tone = 'info',
  title,
  children,
}: {
  tone?: keyof typeof ALERT_TONES
  title?: string
  children?: ReactNode
}) {
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={cx('rounded-lg border p-3 text-sm', ALERT_TONES[tone])}
    >
      {title ? <p className="font-medium">{title}</p> : null}
      {children ? <div className={title ? 'mt-1' : undefined}>{children}</div> : null}
    </div>
  )
}

/* ---------------------------------------------------------------- Card --- */

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <section className={cx('rounded-xl border border-ink-200 bg-white p-6', className)}>
      {children}
    </section>
  )
}

export function CardTitle({ children, hint }: { children: ReactNode; hint?: string }) {
  return (
    <header className="mb-4">
      <h2 className="text-base font-semibold text-ink-900">{children}</h2>
      {hint ? <p className="mt-1 text-sm text-ink-600">{hint}</p> : null}
    </header>
  )
}

/* --------------------------------------------------------------- Badge --- */

const BADGE_TONES = {
  neutral: 'bg-ink-100 text-ink-600',
  brand: 'bg-brand-50 text-brand-700',
  success: 'bg-ok-50 text-ok-600',
  warning: 'bg-warn-50 text-warn-600',
  danger: 'bg-bad-50 text-bad-600',
} as const

export function Badge({
  tone = 'neutral',
  children,
}: {
  tone?: keyof typeof BADGE_TONES
  children: ReactNode
}) {
  return (
    <span
      className={cx(
        'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
        BADGE_TONES[tone],
      )}
    >
      {children}
    </span>
  )
}

/* ---------------------------------------------------------------- Misc --- */

export function PageHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <header className="mb-6">
      <h1 className="text-2xl font-semibold tracking-tight text-ink-900">{title}</h1>
      {subtitle ? <p className="mt-1 text-ink-600">{subtitle}</p> : null}
    </header>
  )
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-ink-200 bg-white p-10 text-center">
      <p className="font-medium text-ink-800">{title}</p>
      {children ? <div className="mt-1 text-sm text-ink-600">{children}</div> : null}
    </div>
  )
}
