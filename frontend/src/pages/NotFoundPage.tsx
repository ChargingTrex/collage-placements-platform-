import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return (
    <div className="flex min-h-full items-center justify-center px-6 py-24 text-center">
      <div>
        <p className="text-sm font-medium text-brand-600">404</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">Page not found</h1>
        <Link to="/" className="mt-4 inline-block text-sm text-brand-600 hover:underline">
          Back to the portal
        </Link>
      </div>
    </div>
  )
}
