import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router'
import { AppLayout } from './components/layout/AppLayout'
import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { AuthPage } from './pages/AuthPage'
import { DashboardPage } from './pages/DashboardPage'
import { SettingsPage } from './pages/SettingsPage'
import { ProfilePage } from './pages/ProfilePage'
import { JobMatchingPage } from './pages/JobMatchingPage'
import { ProductDiscoveryPage } from './pages/ProductDiscoveryPage'
import { ProjectWorkspacePage } from './pages/ProjectWorkspacePage'
import { InterviewPracticePage } from './pages/InterviewPracticePage'
import { GrowthCenterPage } from './pages/GrowthCenterPage'
import { ApplicationWorkspacePage } from './pages/ApplicationWorkspacePage'
import { routes } from './routes'

const CareerProfilePage = lazy(() => import('./pages/CareerProfilePage')
  .then(({ CareerProfilePage }) => ({ default: CareerProfilePage })))

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path={routes.login.path} element={<AuthPage key="login" mode="login" />} />
        <Route path={routes.register.path} element={<AuthPage key="register" mode="register" />} />
        <Route element={<ProtectedRoute />}>
          <Route path={routes.interests.path} element={<ProductDiscoveryPage />} />
          <Route path={routes.projects.path} element={<ProductDiscoveryPage />} />
          <Route path={routes.workspace.path} element={<ProjectWorkspacePage />} />
          <Route path={routes.interview.path} element={<InterviewPracticePage />} />
          <Route path={routes.growth.path} element={<GrowthCenterPage />} />
          <Route path={routes.jobs.path} element={<JobMatchingPage />} />
          <Route path={routes.applications.path} element={<ApplicationWorkspacePage />} />
          <Route path={routes.profile.path} element={<ProfilePage />} />
          <Route path={routes.settings.path} element={<SettingsPage />} />
          <Route path={routes.career.path} element={
            <Suspense fallback={<p role="status">正在加载职业画像页面…</p>}><CareerProfilePage /></Suspense>
          } />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to={routes.dashboard.path} replace />} />
    </Routes>
  )
}
