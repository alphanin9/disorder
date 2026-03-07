import { fireEvent, screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { AppLayout } from "@/features/layout/AppLayout";
import { renderWithProviders } from "@/test/render";

describe("AppLayout", () => {
  it("toggles dark mode and persists the preference", () => {
    renderWithProviders(
      <Routes>
        <Route path="/" element={<AppLayout />}>
          <Route index element={<div>Overview</div>} />
        </Route>
      </Routes>,
    );

    const toggle = screen.getByRole("button", { name: /switch to dark mode/i });

    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(window.localStorage.getItem("disorder-theme")).toBe("light");

    fireEvent.click(toggle);

    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(window.localStorage.getItem("disorder-theme")).toBe("dark");
    expect(screen.getByRole("button", { name: /switch to light mode/i })).toBeInTheDocument();
  });
});
