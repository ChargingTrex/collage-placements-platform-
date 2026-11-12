import { Card, CardTitle, PageHeader } from '@/components/ui'
import { useAuth } from '@/auth/AuthContext'

export default function CompanyHome() {
  const { user } = useAuth()

  return (
    <>
      <PageHeader
        title={user?.full_name || 'Recruiter'}
        subtitle="Browse standardised student profiles instead of a folder of resume PDFs."
      />

      <Card>
        <CardTitle hint="Students control whether their profile is visible to you.">
          Student search
        </CardTitle>
        <p className="text-sm text-ink-600">
          Filter by department, skills, CGPA range and project keywords.
        </p>
      </Card>
    </>
  )
}
