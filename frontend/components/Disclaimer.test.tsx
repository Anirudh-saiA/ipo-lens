import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Disclaimer } from "@/components/Disclaimer";
import { OutputLabel } from "@/components/OutputLabel";

describe("Disclaimer", () => {
  it("says it is a research aid", () => {
    render(<Disclaimer />);
    expect(screen.getByRole("note").textContent).toBe("Research aid, not investment advice.");
  });
});

describe("OutputLabel", () => {
  it("shows a short name and keeps the full label for screen readers and hover", () => {
    render(<OutputLabel label="calculated metric" />);
    const chip = screen.getByText("Calculated metric");
    expect(chip.getAttribute("title")).toBe("calculated metric");
  });
});
