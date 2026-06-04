import { render, screen } from "@testing-library/react";

import type { ClaudeAuthFile } from "@/api/models";
import { ClaudeUsage } from "@/features/integrations/ClaudeUsage";

function authFile(usageSnapshot: ClaudeAuthFile["usage_snapshot"]): ClaudeAuthFile {
  return {
    id: "file-1",
    tag: "default",
    file_name: ".credentials.json",
    sha256: "abc",
    size_bytes: 100,
    uploaded_at: "2026-06-04T00:00:00Z",
    usage_snapshot: usageSnapshot,
  };
}

describe("ClaudeUsage", () => {
  it("renders Claude OAuth usage windows", () => {
    render(
      <ClaudeUsage
        file={authFile({
          five_hour: {
            utilization: 98,
            resets_at: "2099-01-01T00:00:00Z",
          },
          seven_day: {
            utilization: 18,
            resets_at: "2099-01-07T00:00:00Z",
          },
          extra_usage: {
            is_enabled: false,
            utilization: null,
            used_credits: null,
            monthly_limit: null,
            currency: null,
            disabled_reason: null,
          },
        })}
      />,
    );

    expect(screen.getByText("Current usage")).toBeInTheDocument();
    expect(screen.getByText("5h window")).toBeInTheDocument();
    expect(screen.getByText(/98% used/)).toBeInTheDocument();
    expect(screen.getByText("7d window")).toBeInTheDocument();
    expect(screen.getByText(/18% used/)).toBeInTheDocument();
  });

  it("renders nothing when usage has no displayable values", () => {
    const { container } = render(
      <ClaudeUsage
        file={authFile({
          five_hour: null,
          seven_day: null,
          extra_usage: {
            is_enabled: false,
            utilization: null,
            used_credits: null,
            monthly_limit: null,
            currency: null,
            disabled_reason: null,
          },
        })}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
