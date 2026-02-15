import { NavLink, Outlet } from "react-router-dom";

export function AppLayout() {
  return (
    <div className="mx-auto max-w-6xl px-4 pb-8 pt-6 sm:px-6 lg:px-8">
      <header className="mb-6 rounded-2xl border border-slate-200 bg-white px-6 py-4 shadow-panel">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-ink">Disorder CTF Harness</h1>
            <p className="text-sm text-slate-600">Operator console for challenge runs</p>
          </div>
          <nav className="flex items-center gap-2">
            <NavLink
              to="/"
              className={({ isActive }) =>
                `rounded-md px-3 py-2 text-sm font-semibold ${isActive ? "bg-accent text-white" : "text-slate-700 hover:bg-slate-100"}`
              }
            >
              Challenges
            </NavLink>
            <NavLink
              to="/ctfs"
              className={({ isActive }) =>
                `rounded-md px-3 py-2 text-sm font-semibold ${isActive ? "bg-accent text-white" : "text-slate-700 hover:bg-slate-100"}`
              }
            >
              CTFs
            </NavLink>
            <NavLink
              to="/runs"
              className={({ isActive }) =>
                `rounded-md px-3 py-2 text-sm font-semibold ${isActive ? "bg-accent text-white" : "text-slate-700 hover:bg-slate-100"}`
              }
            >
              Runs
            </NavLink>
          </nav>
        </div>
      </header>
      <Outlet />
    </div>
  );
}
