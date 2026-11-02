import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Home from "@/app/page";

describe("Home", () => {
  it("shows the research-aid disclaimer", () => {
    render(<Home />);
    expect(screen.getByRole("note").textContent).toBe("Research aid, not investment advice.");
  });
});
