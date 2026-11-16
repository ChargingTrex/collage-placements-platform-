import { Navigate, Route, Routes } from 'react-router-dom'

import { AuthProvider, homePathFor, useAuth } from '@/auth/AuthContext'
import { RedirectIfSignedIn, RequireAuth, RequireRole } from '@/auth/guards'
import AppShell from '@/components/AppShell'
import SiteFooter from '@/components/SiteFooter'
import LandingPage from '@/pages/LandingPage'
import LoginPage from '@/pages/LoginPage'
import NotFoundPage from '@/pages/NotFoundPage'
import SignupPage from '@/pages/SignupPage'
import VerifyPage from '@/pages/VerifyPage'
import AdminHome from '@/pages/admin/AdminHome'
import FlaggedSignupsPage from '@/pages/admin/FlaggedSignupsPage'
import RosterPage from '@/pages/admin/RosterPage'
import OutcomesPage from '@/pages/admin/OutcomesPage'
import ProfileDetailPage from '@/pages/admin/ProfileDetailPage'
import ProfilesPage from '@/pages/admin/ProfilesPage'
import UsersPage from '@/pages/admin/UsersPage'
import AllOpportunitiesPage from '@/pages/admin/AllOpportunitiesPage'
import OpportunityReviewPage from '@/pages/admin/OpportunityReviewPage'
import OpportunityStatsPage from '@/pages/admin/OpportunityStatsPage'
import ApplicantsPage from '@/pages/company/ApplicantsPage'
import OpportunitiesPage from '@/pages/company/OpportunitiesPage'
import ApplicationsPage from '@/pages/student/ApplicationsPage'
import JobsPage from '@/pages/student/JobsPage'
import NotificationsPage from '@/pages/student/NotificationsPage'
import CompanyHome from '@/pages/company/CompanyHome'
import StudentDetailPage from '@/pages/company/StudentDetailPage'
import StudentSearchPage from '@/pages/company/StudentSearchPage'
import OnboardingPage from '@/pages/student/OnboardingPage'
import ProfilePage from '@/pages/student/ProfilePage'
import StudentHome from '@/pages/student/StudentHome'

/** Signed-in areas share the nav shell; signed-out screens stand alone. */
function Shell({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <AppShell>{children}</AppShell>
    </RequireAuth>
  )
}

function Root() {
  const { user, loading } = useAuth()
  if (loading) return <p className="px-6 py-16 text-center text-sm text-ink-400">Loading…</p>
  return user ? <Navigate to={homePathFor(user)} replace /> : <LandingPage />
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Root />} />

      <Route
        path="/login"
        element={
          <RedirectIfSignedIn>
            <LoginPage />
          </RedirectIfSignedIn>
        }
      />
      <Route
        path="/signup"
        element={
          <RedirectIfSignedIn>
            <SignupPage />
          </RedirectIfSignedIn>
        }
      />
      <Route path="/verify" element={<VerifyPage />} />

      <Route
        path="/student"
        element={
          <Shell>
            <RequireRole role="student">
              <StudentHome />
            </RequireRole>
          </Shell>
        }
      />

      <Route
        path="/student/profile"
        element={
          <Shell>
            <RequireRole role="student">
              <ProfilePage />
            </RequireRole>
          </Shell>
        }
      />

      <Route
        path="/student/onboarding"
        element={
          <Shell>
            <RequireRole role="student">
              <OnboardingPage />
            </RequireRole>
          </Shell>
        }
      />

      <Route
        path="/admin"
        element={
          <Shell>
            <RequireRole role="admin">
              <AdminHome />
            </RequireRole>
          </Shell>
        }
      />
      <Route
        path="/admin/roster"
        element={
          <Shell>
            <RequireRole role="admin">
              <RosterPage />
            </RequireRole>
          </Shell>
        }
      />
      <Route
        path="/admin/flagged"
        element={
          <Shell>
            <RequireRole role="admin">
              <FlaggedSignupsPage />
            </RequireRole>
          </Shell>
        }
      />

      <Route
        path="/admin/profiles"
        element={
          <Shell>
            <RequireRole role="admin">
              <ProfilesPage />
            </RequireRole>
          </Shell>
        }
      />

      <Route
        path="/admin/outcomes"
        element={
          <Shell>
            <RequireRole role="admin">
              <OutcomesPage />
            </RequireRole>
          </Shell>
        }
      />
      <Route
        path="/admin/users"
        element={
          <Shell>
            <RequireRole role="admin">
              <UsersPage />
            </RequireRole>
          </Shell>
        }
      />
      <Route
        path="/admin/profiles/:studentId"
        element={
          <Shell>
            <RequireRole role="admin">
              <ProfileDetailPage />
            </RequireRole>
          </Shell>
        }
      />

      <Route
        path="/company"
        element={
          <Shell>
            <RequireRole role="company">
              <CompanyHome />
            </RequireRole>
          </Shell>
        }
      />

      <Route
        path="/company/students"
        element={
          <Shell>
            <RequireRole role="company">
              <StudentSearchPage />
            </RequireRole>
          </Shell>
        }
      />
      <Route
        path="/company/students/:studentId"
        element={
          <Shell>
            <RequireRole role="company">
              <StudentDetailPage />
            </RequireRole>
          </Shell>
        }
      />

      {/* Phase B: opportunities. Stage 3 (suggestions) and 4 (exports) add routes here. */}
      <Route path="/student/jobs" element={<Shell><RequireRole role="student"><JobsPage /></RequireRole></Shell>} />
      <Route path="/student/applications" element={<Shell><RequireRole role="student"><ApplicationsPage /></RequireRole></Shell>} />
      <Route path="/student/notifications" element={<Shell><RequireRole role="student"><NotificationsPage /></RequireRole></Shell>} />

      <Route path="/company/opportunities" element={<Shell><RequireRole role="company"><OpportunitiesPage /></RequireRole></Shell>} />
      <Route path="/company/opportunities/:opportunityId/applicants" element={<Shell><RequireRole role="company"><ApplicantsPage /></RequireRole></Shell>} />

      <Route path="/admin/opportunities" element={<Shell><RequireRole role="admin"><AllOpportunitiesPage /></RequireRole></Shell>} />
      <Route path="/admin/opportunities/review" element={<Shell><RequireRole role="admin"><OpportunityReviewPage /></RequireRole></Shell>} />
      <Route path="/admin/opportunities/stats" element={<Shell><RequireRole role="admin"><OpportunityStatsPage /></RequireRole></Shell>} />
      <Route path="/admin/opportunities/:opportunityId/applicants" element={<Shell><RequireRole role="admin"><ApplicantsPage /></RequireRole></Shell>} />

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      {/* A column so the footer sits under short pages instead of mid-screen. */}
      <div className="flex min-h-screen flex-col">
        <div className="flex-1">
          <AppRoutes />
        </div>
        <SiteFooter />
      </div>
    </AuthProvider>
  )
}
