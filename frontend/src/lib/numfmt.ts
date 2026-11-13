/**
 * One place for how numbers are shown (the same rules as the Python side, ipo_engine/numfmt.py):
 * Indian digit grouping, ₹ crore with two decimals, a true minus sign, fixed decimals in a column,
 * explicit signs only for changes. Rounding is exact on the decimal digits (half up, like the
 * Python side), never through binary floats, so -3.05 is -3.1 and 1.005 is 1.01.
 */
export const MINUS = "−";

type Dec = { neg: boolean; int: string; frac: string };

function parts(value: number | string): Dec | null {
  let s = typeof value === "number" ? (Number.isFinite(value) ? value.toString() : "") : value.trim();
  if (/e/i.test(s)) s = Number(s).toFixed(12);
  const m = /^([+-]?)(\d*)(?:\.(\d*))?$/.exec(s);
  if (!m || (m[2] === "" && !m[3])) return null;
  return { neg: m[1] === "-", int: m[2] || "0", frac: m[3] ?? "" };
}

/** Round half up to `places` decimals; returns the magnitude as digits and whether it is zero. */
function roundHalfUp(d: Dec, places: number): { text: string; zero: boolean } {
  const frac = d.frac.padEnd(places + 1, "0");
  let scaled = BigInt(d.int + frac.slice(0, places));
  if (frac.charCodeAt(places) >= 53) scaled += 1n; // next digit 5..9
  const digits = scaled.toString().padStart(places + 1, "0");
  const whole = digits.slice(0, digits.length - places);
  const text = places ? `${whole}.${digits.slice(-places)}` : whole;
  return { text, zero: scaled === 0n };
}

function groupIndian(whole: string): string {
  if (whole.length <= 3) return whole;
  const tail = whole.slice(-3);
  let head = whole.slice(0, -3);
  const groups: string[] = [];
  while (head.length > 2) {
    groups.unshift(head.slice(-2));
    head = head.slice(0, -2);
  }
  if (head) groups.unshift(head);
  return `${groups.join(",")},${tail}`;
}

/** 12345678.5 -> "1,23,45,678.50". Accepts a number or a decimal string; never throws. */
export function formatIndian(value: number | string, places = 2): string {
  const d = parts(value);
  if (!d) return "—";
  const r = roundHalfUp(d, places);
  const [whole, frac] = r.text.split(".");
  const body = frac ? `${groupIndian(whole!)}.${frac}` : groupIndian(whole!);
  return `${d.neg && !r.zero ? MINUS : ""}${body}`;
}

/** Like formatIndian but keeps every printed decimal (at least `min`, at most `max`): for values
 *  read from a document, which must not be rounded away. */
export function formatExact(value: number | string, min = 2, max = 4): string {
  const d = parts(value);
  if (!d) return "—";
  const places = Math.min(max, Math.max(min, d.frac.replace(/0+$/, "").length));
  return formatIndian(value, places);
}

/** Rupees (a decimal string, as the API sends money) as ₹ crore, two decimals. */
export function formatCrore(rupees: number | string, places = 2): string {
  const d = parts(rupees);
  if (!d) return "—";
  // divide by 10^7 exactly, by moving the decimal point seven places left
  const all = d.int + d.frac;
  const cut = d.int.length - 7;
  const int = cut > 0 ? all.slice(0, cut) : "0";
  const frac = cut > 0 ? all.slice(cut) : "0".repeat(-cut) + all;
  return formatIndian(`${d.neg ? "-" : ""}${int}.${frac}`, places);
}

/** A percentage; `signed` marks changes with + or a true minus. */
export function formatPercent(value: number | string, places = 1, signed = false): string {
  const d = parts(value);
  if (!d) return "—";
  const r = roundHalfUp(d, places);
  const sign = r.zero ? "" : d.neg ? MINUS : signed ? "+" : "";
  return `${sign}${r.text}%`;
}

/** True when a formatted number is negative (for colouring losses). */
export const isNegative = (formatted: string): boolean => formatted.startsWith(MINUS);
