import { type ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { useGenerationTasks } from "../lib/generationTasks";
import { isAdminContext } from "../lib/permissions";

const NAV_GROUPS: Array<{
  title: string;
  adminOnly?: boolean;
  collapsible?: boolean;
  items: Array<{ to: string; label: string }>;
}> = [
  {
    title: "Workflows",
    items: [
      { to: "/insurance-verification", label: "Insurance Verification" },
      { to: "/denial-letters", label: "Denial Letters" },
      { to: "/email-thread", label: "Email Exchange" }
    ]
  },
  {
    title: "Setup",
    collapsible: true,
    items: [{ to: "/template-library", label: "Template Library" }]
  },
  {
    title: "Administration",
    adminOnly: true,
    collapsible: true,
    items: [{ to: "/model-settings", label: "Admin Console" }]
  },
  {
    title: "Operations",
    adminOnly: true,
    collapsible: true,
    items: [{ to: "/system-health", label: "System Health" }]
  }
];

type AppShellProps = {
  children: ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  const { user, logout, bootstrap } = useAuth();
  const { tasks } = useGenerationTasks();
  const location = useLocation();
  const hasAdminAccess = isAdminContext(user, bootstrap);
  const navGroups = NAV_GROUPS.filter((group) => !group.adminOnly || hasAdminAccess);
  const identityLabel = user ? `${user.username} (${user.role})` : "local-system (admin)";
  const runningCount = Object.values(tasks).filter((task) => task.status === "running").length;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link to="/insurance-verification" className="brand">
          <span className="brand-mark">SD</span>
          <div>
            <p className="brand-title">Siligent Dental AI</p>
            <p className="brand-subtitle">Front Office Workspace</p>
          </div>
        </Link>
        <nav className="sidebar-nav" aria-label="Primary">
          {navGroups.map((group) => (
            group.collapsible ? (
              <details
                className="nav-details"
                key={group.title}
                open={group.items.some((item) => location.pathname.startsWith(item.to)) || undefined}
              >
                <summary className="nav-section-title">{group.title}</summary>
                <div className="nav-section">
                  {group.items.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
                    >
                      {item.label}
                    </NavLink>
                  ))}
                </div>
              </details>
            ) : (
              <div className="nav-section" key={group.title}>
                <p className="nav-section-title">{group.title}</p>
                {group.items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
                  >
                    {item.label}
                  </NavLink>
                ))}
              </div>
            )
          ))}
        </nav>
        <div className="sidebar-footer">
          <p className="helper">
            Signed in as <strong>{identityLabel}</strong>
          </p>
          {user ? (
            <button className="secondary-btn" type="button" onClick={() => void logout()}>
              Sign Out
            </button>
          ) : (
            <p className="helper">Auth disabled mode</p>
          )}
        </div>
      </aside>
      <main className="content">
        {runningCount > 0 ? (
          <div className="status-banner" role="status" aria-live="polite">
            {runningCount} generation task{runningCount > 1 ? "s are" : " is"} running in the background. You can
            switch tabs safely.
          </div>
        ) : null}
        {children}
      </main>
    </div>
  );
}
