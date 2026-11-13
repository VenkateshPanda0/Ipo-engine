import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReaderBrief } from "@/components/report/ReaderBrief";
import { api, type ReaderStatus } from "@/lib/api";

const wrap = (ui: ReactNode) =>
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>);

const ready: ReaderStatus = {
  document_id: "d1",
  reader_version: "15.29",
  status: "ready",
  error: null,
  brief: {
    issue: [["Fresh issue", "21500000000", 1]],
    metrics: [{ label: "Revenue from operations", cells: [["FY2026", "159133200000", 88], ["FY2025", "113318600000", 88]], growth_pct: "40.4" }],
    read_first: [
      { rank: 2, kind: "related_party", text: "A related-party transaction is printed at 12.96% of revenue.", page: 70, evidence: [[70, "Plenova | 945.41 | 12.96%"]], section: "Summary Of Related Party Transactions" },
    ],
    rules_checked: [4, 7],
    numbers_verified: [308, 308],
    notes: ["Related-party summary read."],
    pages: 474,
    sections: [],
  },
};

afterEach(() => vi.restoreAllMocks());

describe("ReaderBrief", () => {
  it("offers to read the document, and starts the reader once", async () => {
    vi.spyOn(api, "readerBrief").mockResolvedValue({ ...ready, status: "not_started", brief: null });
    const start = vi.spyOn(api, "startReader").mockResolvedValue({ ...ready, status: "running", brief: null });
    wrap(<ReaderBrief documentId="d1" canPreview onOpenPage={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: "Read the document" }));
    await waitFor(() => expect(start).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole("status")).toHaveTextContent("Reading the document");
  });

  it("lists what to read first with page buttons that open the page", async () => {
    vi.spyOn(api, "readerBrief").mockResolvedValue(ready);
    const open = vi.fn();
    wrap(<ReaderBrief documentId="d1" canPreview onOpenPage={open} />);
    expect(await screen.findByText(/12\.96% of revenue\./)).toBeInTheDocument();
    expect(screen.getByText("2,150.00")).toBeInTheDocument();
    expect(screen.getByText(/4 of 7 applicable rules/)).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "p.70" })[0]!);
    expect(open).toHaveBeenCalledWith(70);
  });

  it("does not offer page previews or a run when the stored file is gone", async () => {
    vi.spyOn(api, "readerBrief").mockResolvedValue({ ...ready, status: "not_started", brief: null });
    wrap(<ReaderBrief documentId="d1" canPreview={false} onOpenPage={() => {}} />);
    expect(await screen.findByRole("button", { name: "Read the document" })).toBeDisabled();
  });

  it("shows a failure and lets the user try again", async () => {
    vi.spyOn(api, "readerBrief").mockResolvedValue({ ...ready, status: "failed", brief: null, error: "ValueError: bad page" });
    wrap(<ReaderBrief documentId="d1" canPreview onOpenPage={() => {}} />);
    expect(await screen.findByText("ValueError: bad page")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled();
  });
});
