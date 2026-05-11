import { describe, it, expect } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { webcrypto } from "node:crypto";
import { App } from "../src/App";
import realReview from "../../../demo-repo/.profiler/review/review-items.json";
import realSource from "../../../demo-repo/CLAUDE.md?raw";
import type { ReviewArtifact, Evidence } from "../src/types";

const subtle = (globalThis.crypto?.subtle ?? webcrypto.subtle) as SubtleCrypto;

async function sha256(text: string): Promise<string> {
  const digest = await subtle.digest("SHA-256", new TextEncoder().encode(text));
  return (
    "sha256:" +
    Array.from(new Uint8Array(digest))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("")
  );
}

const ev1: Evidence = {
  id: "ev-a00001",
  kind: "trace",
  context_variant: "full",
  label: "run-001",
  source: ".profiler/runs/tasks/t1/run-001/output/sdk-events.jsonl",
  excerpt: "Used pathlib throughout.",
  explanation: "Followed.",
};

const ev2: Evidence = {
  id: "ev-b00001",
  kind: "absence",
  context_variant: "full",
  label: "no deploy runs",
  source: ".profiler/attribution/instruction-evidence.json",
  excerpt: "Zero tool calls referenced deploy/.",
  explanation: "Not observed.",
};

const evAblation: Evidence = {
  id: "ev-c00001",
  kind: "ablation",
  context_variant: "ablate:instr-aaaaaaaa",
  label: "ablation behaved identically",
  source: ".profiler/runs/tasks/t1/run-002/output/sdk-events.jsonl",
  excerpt: "With instruction removed, agent still used pathlib.",
  explanation: "No behavioral change on removal.",
};

const fixtureReview: ReviewArtifact = {
  version: 1,
  source: {
    repoName: "csv-stats",
    contextPath: "CLAUDE.md",
    contextHash: "sha256:aaa",
    generatedAt: "2026-05-10T12:00:00Z",
  },
  summary: {
    totalInstructions: 2,
    totalRuns: 1,
    verdictCounts: { keep: 1, update: 0, remove: 1, add_test: 0 },
    statusCounts: { supported: 1, unobserved: 1 },
    flagCounts: { conflicting: 0, stale: 1 },
    estimatedTokenChange: -3,
  },
  items: [
    {
      id: "instr-aaaaaaaa",
      verdict: "keep",
      status: "supported",
      flags: [],
      title: "Keep this",
      snippet: "Keep me.",
      sourceFile: "CLAUDE.md",
      startOffset: 11,
      endOffset: 19,
      tokenCount: 3,
      tokenDelta: 0,
      metrics: { sessionsObserved: 1, totalSessions: 1, traceEvents: 1 },
      reason: "Followed in trace.",
      evidence: [ev1, evAblation],
    },
    {
      id: "instr-bbbbbbbb",
      verdict: "remove",
      status: "unobserved",
      flags: ["stale"],
      title: "Remove this",
      snippet: "Remove me.",
      sourceFile: "CLAUDE.md",
      startOffset: 21,
      endOffset: 31,
      tokenCount: 3,
      tokenDelta: -3,
      metrics: { sessionsObserved: 0, totalSessions: 1, traceEvents: 0 },
      reason: "Not observed and stale.",
      evidence: [ev2],
      proposedChange: { kind: "remove", rationale: "Dead context." },
    },
  ],
};

const fixtureSource = "# Project\n\nKeep me.\n\nRemove me.\n";

describe("Header", () => {
  it("renders title, repo path, and run statistics in the document column", () => {
    const { container } = render(<App review={fixtureReview} source={fixtureSource} />);
    expect(screen.getByRole("heading", { name: /dead and conflicting instructions/i })).toBeInTheDocument();
    expect(screen.getByText(/csv-stats \/ CLAUDE\.md/)).toBeInTheDocument();
    expect(container.textContent).toContain("2 instructions");
    expect(container.textContent).toContain("1 baseline");
    expect(container.textContent).toContain("2 ablations");
    expect(container.textContent).toContain("1 keep");
    expect(container.textContent).toContain("1 removal");
  });
});

describe("Source document", () => {
  it("renders the full source text including the unhighlighted parts", () => {
    const { container } = render(<App review={fixtureReview} source={fixtureSource} />);
    expect(container.textContent).toContain("# Project");
    expect(container.textContent).toContain("Keep me.");
    expect(container.textContent).toContain("Remove me.");
  });

  it("renders one highlighted span per review item, carrying the original snippet text", () => {
    render(<App review={fixtureReview} source={fixtureSource} />);
    const keep = screen.getByTestId("hl-instr-aaaaaaaa");
    const remove = screen.getByTestId("hl-instr-bbbbbbbb");
    expect(keep.dataset.verdict).toBe("keep");
    expect(remove.dataset.verdict).toBe("remove");
    expect(keep.textContent).toContain("Keep me.");
    expect(remove.textContent).toContain("Remove me.");
  });

  it("renders a terse state label near each highlight that reflects the most salient signal", () => {
    render(<App review={fixtureReview} source={fixtureSource} />);
    expect(screen.getByTestId("hl-tag-instr-aaaaaaaa")).toHaveTextContent(/observed 1\/1 baseline/);
    expect(screen.getByTestId("hl-tag-instr-bbbbbbbb")).toHaveTextContent(/stale · 0\/1 baseline/);
  });

  it("uses verdict-specific labels for add_test, conflict, and not seen", () => {
    const review: ReviewArtifact = {
      ...fixtureReview,
      summary: {
        ...fixtureReview.summary,
        totalInstructions: 3,
        verdictCounts: { keep: 1, update: 1, remove: 0, add_test: 1 },
        statusCounts: { supported: 2, unobserved: 1 },
        flagCounts: { conflicting: 1, stale: 0 },
      },
      items: [
        {
          ...fixtureReview.items[0],
          id: "instr-cccccccc",
          verdict: "add_test",
          status: "supported",
          flags: [],
          startOffset: 11,
          endOffset: 19,
        },
        {
          ...fixtureReview.items[0],
          id: "instr-dddddddd",
          verdict: "update",
          status: "supported",
          flags: ["conflicting"],
          startOffset: 21,
          endOffset: 31,
        },
        {
          ...fixtureReview.items[0],
          id: "instr-eeeeeeee",
          verdict: "keep",
          status: "unobserved",
          flags: [],
          metrics: { sessionsObserved: 0, totalSessions: 4, traceEvents: 0 },
          startOffset: 33,
          endOffset: 33,
        },
      ],
    };
    render(<App review={review} source={fixtureSource} />);
    expect(screen.getByTestId("hl-tag-instr-cccccccc")).toHaveTextContent(/add test/);
    expect(screen.getByTestId("hl-tag-instr-dddddddd")).toHaveTextContent(/conflict/);
    expect(screen.getByTestId("hl-tag-instr-eeeeeeee")).toHaveTextContent(/not observed/);
  });
});

describe("Popover", () => {
  it("clicking a highlight opens a popover with structured sections", () => {
    render(<App review={fixtureReview} source={fixtureSource} />);
    expect(screen.queryByTestId("popover")).toBeNull();
    fireEvent.click(screen.getByTestId("hl-instr-bbbbbbbb"));
    const po = screen.getByTestId("popover");
    expect(po).toBeInTheDocument();
    expect(screen.getByText("Remove this")).toBeInTheDocument();
    expect(screen.getByText(/RECOMMENDATION/)).toBeInTheDocument();
    expect(screen.getByText(/WHY/)).toBeInTheDocument();
    expect(screen.getByText(/EVIDENCE/)).toBeInTheDocument();
    expect(screen.getByText(/Zero tool calls referenced deploy/)).toBeInTheDocument();
  });

  it("action button is near the top in the recommendation section", () => {
    render(<App review={fixtureReview} source={fixtureSource} />);
    fireEvent.click(screen.getByTestId("hl-instr-bbbbbbbb"));
    expect(screen.getByRole("button", { name: /mark for removal/i })).toBeInTheDocument();
  });

  it("keep item shows 'Keep as-is.' with no action row", () => {
    render(<App review={fixtureReview} source={fixtureSource} />);
    fireEvent.click(screen.getByTestId("hl-instr-aaaaaaaa"));
    expect(screen.getByTestId("popover")).toBeInTheDocument();
    expect(screen.getByText(/Keep as-is/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /mark for/i })).toBeNull();
  });

  it("clicking the action button accepts the decision", () => {
    render(<App review={fixtureReview} source={fixtureSource} />);
    fireEvent.click(screen.getByTestId("hl-instr-bbbbbbbb"));
    fireEvent.click(screen.getByRole("button", { name: /mark for removal/i }));
    expect(screen.getByText(/marked for removal/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /mark for removal/i })).toBeNull();
  });

  it("clearing a decision returns to the undecided state", () => {
    render(<App review={fixtureReview} source={fixtureSource} />);
    fireEvent.click(screen.getByTestId("hl-instr-bbbbbbbb"));
    fireEvent.click(screen.getByRole("button", { name: /mark for removal/i }));
    expect(screen.getByText(/marked for removal/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /undo/i }));
    expect(screen.getByRole("button", { name: /mark for removal/i })).toBeInTheDocument();
  });

  it("decided items show an indicator on the highlight", () => {
    render(<App review={fixtureReview} source={fixtureSource} />);
    fireEvent.click(screen.getByTestId("hl-instr-bbbbbbbb"));
    fireEvent.click(screen.getByRole("button", { name: /mark for removal/i }));
    expect(screen.getByTestId("hl-instr-bbbbbbbb").className).toContain("decided");
  });

  it("close button dismisses the popover", () => {
    render(<App review={fixtureReview} source={fixtureSource} />);
    fireEvent.click(screen.getByTestId("hl-instr-bbbbbbbb"));
    expect(screen.getByTestId("popover")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(screen.queryByTestId("popover")).toBeNull();
  });

  it("first screen has no popover", () => {
    render(<App review={fixtureReview} source={fixtureSource} />);
    expect(screen.queryByTestId("popover")).toBeNull();
  });

  it("clicking outside the popover dismisses it", () => {
    render(<App review={fixtureReview} source={fixtureSource} />);
    fireEvent.click(screen.getByTestId("hl-instr-bbbbbbbb"));
    expect(screen.getByTestId("popover")).toBeInTheDocument();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByTestId("popover")).toBeNull();
  });

  it("Skip dismisses a manually opened popover outside the guided review", () => {
    render(<App review={fixtureReview} source={fixtureSource} />);
    fireEvent.click(screen.getByTestId("hl-instr-bbbbbbbb"));
    expect(screen.getByTestId("popover")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /skip/i }));
    expect(screen.queryByTestId("popover")).toBeNull();
  });

  it("shows all evidence items inline, ablation evidence labeled", () => {
    render(<App review={fixtureReview} source={fixtureSource} />);
    fireEvent.click(screen.getByTestId("hl-instr-aaaaaaaa"));
    expect(screen.getByText(/Used pathlib throughout/)).toBeInTheDocument();
    expect(screen.getByText(/agent still used pathlib/)).toBeInTheDocument();
    expect(screen.getByText("ABLATION")).toBeInTheDocument();
  });

  it("clicking a different highlight switches the popover", () => {
    render(<App review={fixtureReview} source={fixtureSource} />);
    fireEvent.click(screen.getByTestId("hl-instr-bbbbbbbb"));
    expect(screen.getByText("Remove this")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("hl-instr-aaaaaaaa"));
    expect(screen.getByText("Keep this")).toBeInTheDocument();
    expect(screen.queryByText("Remove this")).toBeNull();
  });
});

describe("Review flow", () => {
  it("shows Start Review button before review begins", () => {
    render(<App review={fixtureReview} source={fixtureSource} />);
    expect(screen.getByRole("button", { name: /review 1 recommendation/i })).toBeInTheDocument();
    expect(screen.getAllByText(/1 removal/i).length).toBeGreaterThanOrEqual(1);
  });

  it("Start Review opens the popover on the first reviewable item", () => {
    render(<App review={fixtureReview} source={fixtureSource} />);
    fireEvent.click(screen.getByRole("button", { name: /review 1 recommendation/i }));
    expect(screen.getByTestId("popover")).toBeInTheDocument();
    expect(screen.getByText("Remove this")).toBeInTheDocument();
  });

  it("shows completion after deciding all items", () => {
    render(<App review={fixtureReview} source={fixtureSource} />);
    fireEvent.click(screen.getByRole("button", { name: /review 1 recommendation/i }));
    fireEvent.click(screen.getByRole("button", { name: /mark for removal/i }));
    expect(screen.getByText(/review complete/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /accept changes/i })).toBeInTheDocument();
  });

  it("Accept changes shows the summary", () => {
    render(<App review={fixtureReview} source={fixtureSource} />);
    fireEvent.click(screen.getByRole("button", { name: /review 1 recommendation/i }));
    fireEvent.click(screen.getByRole("button", { name: /mark for removal/i }));
    fireEvent.click(screen.getByRole("button", { name: /accept changes/i }));
    expect(screen.getByTestId("summary")).toBeInTheDocument();
    expect(screen.getByText(/Remove this/)).toBeInTheDocument();
  });

  it("skipping all items completes the review", () => {
    render(<App review={fixtureReview} source={fixtureSource} />);
    fireEvent.click(screen.getByRole("button", { name: /review 1 recommendation/i }));
    fireEvent.click(screen.getByRole("button", { name: /skip/i }));
    expect(screen.getByText(/review complete/i)).toBeInTheDocument();
  });

  it("Reset clears decisions and returns to Start Review", () => {
    render(<App review={fixtureReview} source={fixtureSource} />);
    fireEvent.click(screen.getByRole("button", { name: /review 1 recommendation/i }));
    fireEvent.click(screen.getByRole("button", { name: /mark for removal/i }));
    fireEvent.click(screen.getByRole("button", { name: /reset/i }));
    expect(screen.getByRole("button", { name: /review 1 recommendation/i })).toBeInTheDocument();
  });
});

describe("Drift", () => {
  it("warns when source hash and review hash diverge", async () => {
    render(<App review={fixtureReview} source={fixtureSource} />);
    await waitFor(() => screen.getByRole("alert"));
    expect(screen.getByRole("alert")).toHaveTextContent(/re-run the profiler/i);
  });
});

describe("Real artifact integration", () => {
  it("real CLAUDE.md hash matches review.source.contextHash", async () => {
    expect(await sha256(realSource)).toBe(
      (realReview as ReviewArtifact).source.contextHash,
    );
  });

  it("review items' offsets map to real CLAUDE.md spans", () => {
    const review = realReview as ReviewArtifact;
    for (const item of review.items) {
      const actual = realSource.slice(item.startOffset, item.endOffset);
      expect(actual).toBe(item.snippet);
    }
  });

  it("renders the real fixture without a drift alert", async () => {
    render(<App />);
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("renders one highlight per real review item", () => {
    render(<App />);
    for (const item of (realReview as ReviewArtifact).items) {
      const el = screen.getByTestId(`hl-${item.id}`);
      expect(el.textContent).toContain(item.snippet);
    }
  });
});
