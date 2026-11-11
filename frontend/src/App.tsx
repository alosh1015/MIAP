import { Link, Navigate, Route, Routes, useParams } from "react-router-dom";
import { RequireAuth, RequireRole } from "./components/RequireAuth";
import { AppShell } from "./components/shell/AppShell";
import { EmptyState, Panel } from "./components/ui";
import { AdminAuditPage } from "./pages/AdminAuditPage";
import { AdminHealthPage } from "./pages/AdminHealthPage";
import { AdminModelsPage } from "./pages/AdminModelsPage";
import { AdminRetentionPage } from "./pages/AdminRetentionPage";
import { AdminUsersPage } from "./pages/AdminUsersPage";
import { CaseWorkspacePage } from "./pages/CaseWorkspacePage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { ModelLibraryPage } from "./pages/ModelLibraryPage";
import { NewPatientPage } from "./pages/NewPatientPage";
import { NewStudyPage } from "./pages/NewStudyPage";
import { PatientPage } from "./pages/PatientPage";
import { ResearchBatchesPage } from "./pages/ResearchBatchesPage";
import { SettingsPage } from "./pages/SettingsPage";
import { WorklistPage } from "./pages/WorklistPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="worklist" element={<WorklistPage />} />
          <Route path="research" element={<WorklistPage />} />
          <Route
            path="research/batches"
            element={
              <RequireRole roles={["researcher", "clinician"]}>
                <ResearchBatchesPage />
              </RequireRole>
            }
          />
          <Route
            path="patients/new"
            element={
              <RequireRole roles={["clinician"]}>
                <NewPatientPage />
              </RequireRole>
            }
          />
          <Route
            path="patients/:patientId"
            element={
              <RequireRole roles={["clinician"]}>
                <PatientPage />
              </RequireRole>
            }
          />
          <Route
            path="cases/new"
            element={
              <RequireRole roles={["clinician", "researcher"]}>
                <NewStudyPage />
              </RequireRole>
            }
          />
          <Route path="cases/:caseId" element={<CaseWorkspacePage />} />
          <Route path="cases/:caseId/results/:jobId" element={<LegacyResultRedirect />} />
          <Route path="models" element={<ModelLibraryPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="admin" element={<Navigate to="/admin/health" replace />} />
          <Route
            path="admin/health"
            element={
              <RequireRole roles={["administrator"]}>
                <AdminHealthPage />
              </RequireRole>
            }
          />
          <Route
            path="admin/users"
            element={
              <RequireRole roles={["administrator"]}>
                <AdminUsersPage />
              </RequireRole>
            }
          />
          <Route
            path="admin/audit"
            element={
              <RequireRole roles={["administrator"]}>
                <AdminAuditPage />
              </RequireRole>
            }
          />
          <Route
            path="admin/retention"
            element={
              <RequireRole roles={["administrator"]}>
                <AdminRetentionPage />
              </RequireRole>
            }
          />
          <Route
            path="admin/models"
            element={
              <RequireRole roles={["administrator"]}>
                <AdminModelsPage />
              </RequireRole>
            }
          />
          <Route path="audit" element={<Navigate to="/admin/audit" replace />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Route>
    </Routes>
  );
}

function LegacyResultRedirect() {
  const { caseId = "", jobId = "" } = useParams();
  return <Navigate to={`/cases/${caseId}?result=${encodeURIComponent(jobId)}`} replace />;
}

function NotFound() {
  return (
    <Panel>
      <EmptyState
        icon="search"
        title="Page not found"
        action={
          <Link to="/" className="text-sm font-medium text-petrol hover:underline">
            Dashboard
          </Link>
        }
      />
    </Panel>
  );
}
