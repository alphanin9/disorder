import { NavLink, Outlet } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { useTheme } from "@/app/theme";

export function AppLayout() {
  const { theme, toggleTheme } = useTheme();

  return (
    <div className="mx-auto max-w-6xl px-4 pb-8 pt-6 text-ink sm:px-6 lg:px-8">
      <header className="mb-6 rounded-2xl border border-line bg-surface/95 px-6 py-4 shadow-panel backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-ink">Disorder CTF Harness</h1>
            <p className="text-sm text-ink-muted">
              Operator console for challenge runs
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <nav className="flex items-center gap-2">
              <NavLink
                to="/"
                className={({ isActive }) =>
                  `rounded-md px-3 py-2 text-sm font-semibold transition ${isActive ? "bg-accent text-white shadow-sm dark:text-slate-950" : "text-ink-muted hover:bg-surface-muted hover:text-ink"}`
                }
              >
                Challenges
              </NavLink>
              <NavLink
                to="/ctfs"
                className={({ isActive }) =>
                  `rounded-md px-3 py-2 text-sm font-semibold transition ${isActive ? "bg-accent text-white shadow-sm dark:text-slate-950" : "text-ink-muted hover:bg-surface-muted hover:text-ink"}`
                }
              >
                CTFs
              </NavLink>
              <NavLink
                to="/runs"
                className={({ isActive }) =>
                  `rounded-md px-3 py-2 text-sm font-semibold transition ${isActive ? "bg-accent text-white shadow-sm dark:text-slate-950" : "text-ink-muted hover:bg-surface-muted hover:text-ink"}`
                }
              >
                Runs
              </NavLink>
            </nav>
            <Button
              type="button"
              variant="secondary"
              className="min-w-28"
              aria-label={
                theme === "dark"
                  ? "Switch to light mode"
                  : "Switch to dark mode"
              }
              onClick={toggleTheme}
            >
              {theme === "dark" ? "Light mode" : "Dark mode"}
            </Button>
          </div>
        </div>
      </header>
      <Outlet />
    </div>
  );
}
