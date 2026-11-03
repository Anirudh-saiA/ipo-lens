import { describe, expect, it } from "vitest";

import { formatDate, formatNumber, periodName, sortPeriods } from "@/lib/format";

describe("formatNumber", () => {
  it("keeps the printed decimals and groups thousands", () => {
    expect(formatNumber("12668.18", "INR million")).toBe("12,668.18");
    expect(formatNumber("1468853", "INR million")).toBe("1,468,853");
    expect(formatNumber("7.60", "INR per share")).toBe("7.60");
    expect(formatNumber("1250.00", "INR million")).toBe("1,250.00"); // as printed
  });

  it("shows negatives in brackets, as prospectuses do", () => {
    expect(formatNumber("-218.38", "INR million")).toBe("(218.38)");
  });

  it("shows ratios, already rounded by the backend, with their unit", () => {
    expect(formatNumber("29.85", "%")).toBe("29.85%");
    expect(formatNumber("2.78", "x")).toBe("2.78x");
    expect(formatNumber("0.21", "x")).toBe("0.21x");
  });
});

describe("periods", () => {
  it("names periods", () => {
    expect(periodName("FY2026")).toBe("FY2026");
    expect(periodName("3M ended 2026-06-30")).toBe("3M to Jun 2026");
    expect(periodName("as at 2026-03-31")).toBe("Mar 2026");
  });

  it("orders newest first, mixing fiscal years and part years", () => {
    expect(sortPeriods(["FY2024", "3M ended 2026-06-30", "FY2026", "FY2025"])).toEqual([
      "3M ended 2026-06-30",
      "FY2026",
      "FY2025",
      "FY2024",
    ]);
  });

  it("formats dates", () => {
    expect(formatDate("2026-11-02")).toBe("2 Nov 2026");
  });
});
