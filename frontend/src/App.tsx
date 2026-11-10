import { Link, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { RequireAuth, RequireRole } from "./components/RequireAuth";
import { AuditPage } from "./pages/AuditPage";
import { CaseWorkspacePage } from "./pages/CaseWorkspacePage";
import { LoginPage } from "./pages/LoginPage";
import { ModelLibraryPage } from "./pages/ModelLibraryPage";
import { NewCasePage } from "./pages/NewCasePage";
import { ResultsPage } from "./pages/ResultsPage";
import { WorklistPage } from "./pages/WorklistPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<Layout />}>
          <Route index element={<WorklistPage />} />
          <Route
            path="cases/new"
            element={
              <RequireRole roles={["clinician", "researcher"]}>
                <NewCasePage />
              </RequireRole>
            }
          />
          <Route path="cases/:caseId" element={<CaseWorkspacePage />} />
          <Route
            path="cases/:caseId/results/:jobId"
            element={
              <RequireRole roles={["clinician", "researcher"]}>
                <ResultsPage />
              </RequireRole>
            }
          />
          <Route path="models" element={<ModelLibraryPage />} />
          <Route
            path="audit"
            element={
              <RequireRole roles={["administrator"]}>
                <AuditPage />
              </RequireRole>
            }
          />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Route>
    </Routes>
  );
}

function NotFound() {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-10 text-center">
      <p className="text-sm font-semibold text-slate-800">Page not found</p>
      <Link to="/" className="mt-3 inline-block text-sm text-clinical-700 hover:underline">
        Back to the worklist
      </Link>
    </div>
  );
}
