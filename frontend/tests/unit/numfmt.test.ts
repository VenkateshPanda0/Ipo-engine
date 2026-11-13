import { describe, expect, it } from "vitest";
import { MINUS, formatCrore, formatIndian, formatPercent, isNegative } from "@/lib/numfmt";
import { formatValue } from "@/lib/format";

describe("numfmt", () => {
  it("groups in the Indian system with fixed decimals", () => {
    expect(formatIndian(12345678.5)).toBe("1,23,45,678.50");
    expect(formatIndian("999.999")).toBe("1,000.00");
    expect(formatIndian(1234567, 0)).toBe("12,34,567");
    expect(formatIndian("not a number")).toBe("—");
  });
  it("uses a true minus and never shows negative zero", () => {
    expect(formatIndian(-1234.5)).toBe(`${MINUS}1,234.50`);
    expect(formatIndian(-0.001)).toBe("0.00");
    expect(isNegative(formatIndian(-5))).toBe(true);
  });
  it("shows rupees as crore", () => {
    expect(formatCrore("159133200000")).toBe("15,913.32");
    expect(formatCrore("-6815300000")).toBe(`${MINUS}681.53`);
  });
  it("signs only changes", () => {
    expect(formatPercent("40.43")).toBe("40.4%");
    expect(formatPercent("40.43", 1, true)).toBe("+40.4%");
    expect(formatPercent("-3.05", 1, true)).toBe(`${MINUS}3.1%`);
    expect(formatPercent("0.01", 1, true)).toBe("0.0%");
  });
  it("rounds exactly on the decimal digits, like the Python side", () => {
    expect(formatIndian("1.005")).toBe("1.01");
    expect(formatIndian("2.675")).toBe("2.68");
    expect(formatCrore("12345678901")).toBe("1,234.57");
    expect(formatCrore("5000")).toBe("0.00");
    expect(formatCrore("0.5")).toBe("0.00");
  });
  it("never rounds a value read from a document away", () => {
    expect(formatValue("123.4567", "INR_CRORE")).toBe("₹123.4567 Cr");
    expect(formatValue("1234.5", "INR_CRORE")).toBe("₹1,234.50 Cr");
    expect(formatValue("12.9", "PERCENT")).toBe("12.9%");
    expect(formatValue("25", "PERCENT")).toBe("25%");
  });
});
