import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from '@/auth/AuthContext'
import ProtectedRoute from '@/auth/ProtectedRoute'
import AppShell from '@/components/AppShell'
import { homePathFor } from '@/lib/routes'
import AdminAlerts from '@/pages/admin/Alerts'
import AllFindings from '@/pages/admin/AllFindings'
import Deadlines from '@/pages/admin/Deadlines'
import FindingReview from '@/pages/admin/FindingReview'
import Overview from '@/pages/admin/Overview'
import ReviewQueue from '@/pages/admin/ReviewQueue'
import ScanDetail from '@/pages/admin/ScanDetail'
import Scans from '@/pages/admin/Scans'
import SiteDetail from '@/pages/admin/SiteDetail'
import Sites from '@/pages/admin/Sites'
import TicketDetail from '@/pages/admin/TicketDetail'
import Tickets from '@/pages/admin/Tickets'
import VendorDetail from '@/pages/admin/VendorDetail'
import Vendors from '@/pages/admin/Vendors'
import Login from '@/pages/shared/Login'
import NotFound from '@/pages/shared/NotFound'
import Unauthorized from '@/pages/shared/Unauthorized'
import VendorAlerts from '@/pages/vendor/Alerts'
import MyPerformance from '@/pages/vendor/MyPerformance'
import MyTickets from '@/pages/vendor/MyTickets'
import VendorTicketDetail from '@/pages/vendor/VendorTicketDetail'

// "/" sends each person to their own home, or to sign in.
function RootRedirect() {
  const { user, loading } = useAuth()
  if (loading) return <p className="p-8 text-ink-soft">Checking your session</p>
  return <Navigate to={user ? homePathFor(user.role) : '/login'} replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/login" element={<Login />} />
          <Route path="/unauthorized" element={<Unauthorized />} />

          <Route path="/admin" element={<ProtectedRoute role="admin" />}>
            <Route element={<AppShell />}>
              <Route index element={<Overview />} />
              <Route path="findings" element={<ReviewQueue />} />
              <Route path="findings/:id" element={<FindingReview />} />
              <Route path="all-findings" element={<AllFindings />} />
              <Route path="tickets" element={<Tickets />} />
              <Route path="tickets/:id" element={<TicketDetail />} />
              <Route path="sites" element={<Sites />} />
              <Route path="sites/:id" element={<SiteDetail />} />
              <Route path="vendors" element={<Vendors />} />
              <Route path="vendors/:id" element={<VendorDetail />} />
              <Route path="scans" element={<Scans />} />
              <Route path="scans/:id" element={<ScanDetail />} />
              <Route path="alerts" element={<AdminAlerts />} />
              <Route path="deadlines" element={<Deadlines />} />
            </Route>
          </Route>

          <Route path="/vendor" element={<ProtectedRoute role="vendor" />}>
            <Route element={<AppShell />}>
              <Route index element={<MyTickets />} />
              <Route path="tickets/:id" element={<VendorTicketDetail />} />
              <Route path="performance" element={<MyPerformance />} />
              <Route path="alerts" element={<VendorAlerts />} />
            </Route>
          </Route>

          <Route path="*" element={<NotFound />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}