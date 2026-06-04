import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { useAuth } from "./lib/auth";
import { isAdminContext } from "./lib/permissions";
import { InsuranceVerificationPage } from "./pages/InsuranceVerificationPage";
import { LoginPage } from "./pages/LoginPage";
import { ModelSettingsPage } from "./pages/ModelSettingsPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { SmartComposerPage } from "./pages/SmartComposerPage";
import { SystemHealthPage } from "./pages/SystemHealthPage";
import { TemplateLibraryPage } from "./pages/TemplateLibraryPage";

function AppRoutes({ canAccessAdmin }: { canAccessAdmin: boolean }) {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/insurance-verification" replace />} />
      <Route path="/smart-composer" element={<SmartComposerPage />} />
      <Route path="/email-thread" element={<SmartComposerPage />} />
      <Route path="/denial-letters" element={<SmartComposerPage />} />
      <Route path="/insurance-verification" element={<InsuranceVerificationPage />} />
      <Route path="/email-drafting" element={<SmartComposerPage />} />
      <Route path="/template-library" element={<TemplateLibraryPage />} />
      <Route
        path="/model-settings"
        element={canAccessAdmin ? <ModelSettingsPage /> : <Navigate to="/insurance-verification" replace />}
      />
      <Route
        path="/system-health"
        element={canAccessAdmin ? <SystemHealthPage /> : <Navigate to="/insurance-verification" replace />}
      />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

export default function App() {
  const { loading, user, bootstrap } = useAuth();
  const authDisabled = Boolean(bootstrap && !bootstrap.auth_enabled);
  const canAccessAdmin = isAdminContext(user, bootstrap);

  if (loading) {
    return <div className="auth-wrap">Loading...</div>;
  }

  if (!authDisabled && !user) {
    return <LoginPage />;
  }

  return (
    <AppShell>
      <AppRoutes canAccessAdmin={canAccessAdmin} />
    </AppShell>
  );
}
