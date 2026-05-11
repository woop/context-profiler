import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReviewArtifact, ReviewItem } from "./types";
import reviewArtifact from "../../../demo-repo/.profiler/review/review-items.json";
import sourceMarkdown from "../../../demo-repo/CLAUDE.md?raw";

interface Segment {
  text: string;
  item: ReviewItem | null;
}

function buildSegments(source: string, items: ReviewItem[]): Segment[] {
  const sorted = [...items].sort((a, b) => a.startOffset - b.startOffset);
  const segs: Segment[] = [];
  let cursor = 0;
  for (const item of sorted) {
    if (item.startOffset > cursor) {
      segs.push({ text: source.slice(cursor, item.startOffset), item: null });
    }
    segs.push({ text: source.slice(item.startOffset, item.endOffset), item });
    cursor = item.endOffset;
  }
  if (cursor < source.length) {
    segs.push({ text: source.slice(cursor), item: null });
  }
  return segs;
}

async function sha256(text: string): Promise<string> {
  const buf = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", buf);
  return (
    "sha256:" +
    Array.from(new Uint8Array(digest))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("")
  );
}

export interface AppProps {
  review?: ReviewArtifact;
  source?: string;
}

interface PopoverState {
  id: string;
  rect: DOMRect;
  gutterLeft: number;
}

export function App({
  review = reviewArtifact as ReviewArtifact,
  source = sourceMarkdown,
}: AppProps = {}) {
  const [sourceHash, setSourceHash] = useState<string | null>(null);
  const [popover, setPopover] = useState<PopoverState | null>(null);
  const [decisions, setDecisions] = useState<Record<string, string>>({});
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const [reviewStarted, setReviewStarted] = useState(false);
  const [showSummary, setShowSummary] = useState(false);
  const articleRef = useRef<HTMLElement>(null);

  useEffect(() => {
    sha256(source).then(setSourceHash);
  }, [source]);

  const segments = useMemo(
    () => buildSegments(source, review.items),
    [source, review.items],
  );

  const selected = useMemo(
    () => (popover ? review.items.find((i) => i.id === popover.id) ?? null : null),
    [review, popover],
  );

  const reviewable = useMemo(
    () => review.items.filter((i) => i.proposedChange).sort((a, b) => a.startOffset - b.startOffset),
    [review],
  );

  const reviewedCount = useMemo(
    () => reviewable.filter((i) => i.id in decisions || skipped.has(i.id)).length,
    [reviewable, decisions, skipped],
  );

  const allReviewed = reviewable.length > 0 && reviewedCount === reviewable.length;

  const handleSelect = useCallback((id: string, rect: DOMRect) => {
    const gutterLeft = articleRef.current?.getBoundingClientRect().right ?? rect.right;
    setPopover({ id, rect, gutterLeft });
  }, []);

  const dismiss = useCallback(() => setPopover(null), []);

  const navigateTo = useCallback((id: string) => {
    const el = document.querySelector(`[data-testid="hl-${id}"]`) as HTMLElement | null;
    if (!el) return;
    el.scrollIntoView?.({ block: "center" });
    const rect = el.getBoundingClientRect();
    const gutterLeft = articleRef.current?.getBoundingClientRect().right ?? rect.right;
    setPopover({ id, rect, gutterLeft });
  }, []);

  const findNextUndecided = useCallback((afterId?: string | null): string | null => {
    const currentIdx = afterId ? reviewable.findIndex((i) => i.id === afterId) : -1;
    const isResolved = (id: string) => id in decisions || skipped.has(id);
    for (let i = currentIdx + 1; i < reviewable.length; i++) {
      if (!isResolved(reviewable[i].id)) return reviewable[i].id;
    }
    for (let i = 0; i <= currentIdx; i++) {
      if (!isResolved(reviewable[i].id)) return reviewable[i].id;
    }
    return null;
  }, [reviewable, decisions, skipped]);

  const navigateNext = useCallback(() => {
    const nextId = findNextUndecided(popover?.id);
    if (nextId) navigateTo(nextId);
  }, [popover, findNextUndecided, navigateTo]);

  const decide = useCallback((id: string, action: string) => {
    setDecisions((prev) => ({ ...prev, [id]: action }));
  }, []);

  const clearDecision = useCallback((id: string) => {
    setDecisions((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  }, []);

  // Auto-advance after a decision or skip
  useEffect(() => {
    if (!reviewStarted || !popover) return;
    const resolved = popover.id in decisions || skipped.has(popover.id);
    if (!resolved) return;
    const nextId = findNextUndecided(popover.id);
    if (!nextId) {
      dismiss();
      return;
    }
    const timer = setTimeout(() => navigateTo(nextId), 350);
    return () => clearTimeout(timer);
  }, [decisions, skipped, popover?.id, reviewStarted, findNextUndecided, navigateTo, dismiss]);

  const startReview = useCallback(() => {
    setReviewStarted(true);
    const firstId = findNextUndecided(null);
    if (firstId) navigateTo(firstId);
  }, [findNextUndecided, navigateTo]);

  const resetReview = useCallback(() => {
    setDecisions({});
    setSkipped(new Set());
    setReviewStarted(false);
    setPopover(null);
  }, []);

  useEffect(() => {
    if (!popover) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") dismiss();
    };
    const onDown = (e: MouseEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest("[data-testid='popover']")) return;
      dismiss();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [popover, dismiss]);

  const drift =
    sourceHash !== null && sourceHash !== review.source.contextHash;

  if (showSummary) {
    return (
      <div className="app">
        <Summary
          review={review}
          source={source}
          decisions={decisions}
          skipped={skipped}
          reviewable={reviewable}
          onBack={() => setShowSummary(false)}
        />
      </div>
    );
  }

  return (
    <div className="app">
      <main>
        <article ref={articleRef} className="source">
          <DocHeader review={review} drift={drift} />
          <ReviewControls
            started={reviewStarted}
            reviewedCount={reviewedCount}
            totalCount={reviewable.length}
            verdictCounts={review.summary.verdictCounts}
            allReviewed={allReviewed}
            onStart={startReview}
            onNext={navigateNext}
            onAccept={() => setShowSummary(true)}
            onReset={resetReview}
          />
          {drift && (
            <div role="alert" className="drift-banner">
              Source has changed since this report was generated. Re-run the profiler.
            </div>
          )}
          {segments.map((seg, i) =>
            seg.item ? (
              <Highlight
                key={i}
                item={seg.item}
                text={seg.text}
                selected={popover?.id === seg.item.id}
                decided={seg.item.id in decisions}
                onSelect={handleSelect}
              />
            ) : (
              <span key={i}>{seg.text}</span>
            ),
          )}
        </article>
      </main>
      {selected && popover && (
        <Popover
          item={selected}
          anchorRect={popover.rect}
          gutterLeft={popover.gutterLeft}
          decision={decisions[selected.id] ?? null}
          onDecide={(action) => decide(selected.id, action)}
          onClear={() => clearDecision(selected.id)}
          onSkip={() => {
            setSkipped((prev) => new Set(prev).add(selected.id));
            if (!reviewStarted) dismiss();
          }}
          onClose={dismiss}
        />
      )}
    </div>
  );
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}

function plural(count: number, singular: string, pluralForm = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

function DocHeader({ review, drift }: { review: ReviewArtifact; drift: boolean }) {
  const s = review.summary;
  const vc = s.verdictCounts;
  const ablationRuns = s.totalInstructions;
  const recommendationCount = vc.update + vc.remove + vc.add_test;
  const recommendationText = `Found ${plural(recommendationCount, "recommended edit")}: ${plural(vc.update, "testing update")}, ${plural(vc.remove, "removal")} for stale or conflicting guidance`;

  return (
    <div className="doc-header">
      <h1>Find dead and conflicting instructions in CLAUDE.md</h1>
      <span className="dh-path">{review.source.repoName} / {review.source.contextPath}</span>
      <p className="dh-grounding">
        Demo CLAUDE.md from a Python CLI repo, profiled against {s.totalRuns} baseline Claude Code runs and {ablationRuns} ablations. {recommendationText}.
      </p>
      <span className="dh-summary">
        <span tabIndex={0} data-tooltip="Individual rules extracted from the CLAUDE.md">{s.totalInstructions} instructions</span>
        {" · "}
        <span tabIndex={0} data-tooltip="Full-context baseline traces used for evaluation">{s.totalRuns} baseline</span>
        {" · "}
        <span tabIndex={0} data-tooltip="Single-instruction ablation traces used for directional evidence">{ablationRuns} ablations</span>
        {vc.keep > 0 && <>{" · "}<span tabIndex={0} data-tooltip="Instructions that are working as intended">{vc.keep} keep</span></>}
        {vc.update > 0 && <>{" · "}<span tabIndex={0} data-tooltip="Instructions with a suggested rewrite">{vc.update} update</span></>}
        {vc.remove > 0 && <>{" · "}<span tabIndex={0} data-tooltip="Instructions recommended for deletion">{plural(vc.remove, "removal")}</span></>}
        {vc.add_test > 0 && <>{" · "}<span tabIndex={0} data-tooltip="Instructions that need a verification check">{vc.add_test} add test</span></>}
        {" · "}
        {formatDate(review.source.generatedAt)}
      </span>
      {drift && <span className="dh-drift" tabIndex={0} data-tooltip="The source file changed after this report was generated">drift detected</span>}
    </div>
  );
}

function VerdictLegend() {
  return (
    <div className="verdict-legend" aria-label="Verdict legend">
      <span><i className="legend-swatch legend-keep" />keep</span>
      <span><i className="legend-swatch legend-update" />update</span>
      <span><i className="legend-swatch legend-remove" />remove</span>
    </div>
  );
}

function ReviewControls({
  started,
  reviewedCount,
  totalCount,
  verdictCounts,
  allReviewed,
  onStart,
  onNext,
  onAccept,
  onReset,
}: {
  started: boolean;
  reviewedCount: number;
  totalCount: number;
  verdictCounts: ReviewArtifact["summary"]["verdictCounts"];
  allReviewed: boolean;
  onStart: () => void;
  onNext: () => void;
  onAccept: () => void;
  onReset: () => void;
}) {
  if (totalCount === 0) return null;

  if (!started) {
    const recommendationParts = [
      verdictCounts.update > 0 ? plural(verdictCounts.update, "update") : null,
      verdictCounts.remove > 0 ? plural(verdictCounts.remove, "removal") : null,
      verdictCounts.add_test > 0 ? plural(verdictCounts.add_test, "test") : null,
    ].filter(Boolean).join(" · ");

    return (
      <div className="rc" data-testid="review-bar">
        <button type="button" className="rc-start" onClick={onStart}>
          Review {plural(totalCount, "recommendation")}
        </button>
        <span className="rc-hint">{recommendationParts}</span>
        <VerdictLegend />
      </div>
    );
  }

  return (
    <div className="rc" data-testid="review-bar">
      <div className="rc-progress">
        <div className="rc-track">
          <div className="rc-fill" style={{ width: `${(reviewedCount / totalCount) * 100}%` }} />
        </div>
        <span className="rc-count">{reviewedCount}/{totalCount}</span>
      </div>
      {allReviewed ? (
        <div className="rc-done">
          <span className="rc-complete">Review complete</span>
          <button type="button" className="rc-btn rc-btn-primary" onClick={onAccept}>Accept changes</button>
          <button type="button" className="rc-btn" onClick={onReset}>Reset</button>
        </div>
      ) : (
        <button type="button" className="rc-btn" onClick={onNext}>Next</button>
      )}
    </div>
  );
}

function stateLabel(item: ReviewItem): string {
  const runs = `${item.metrics.sessionsObserved}/${item.metrics.totalSessions} baseline`;
  if (item.verdict === "add_test") return `add test · ${runs}`;
  if (item.flags.includes("conflicting")) return `conflict · ${runs}`;
  if (item.flags.includes("stale")) return `stale · ${runs}`;
  if (item.status === "supported") return `observed ${runs}`;
  return `not observed · ${runs}`;
}

function stateLabelTooltip(item: ReviewItem): string {
  if (item.verdict === "add_test") return "This instruction needs a verification check to be enforceable";
  if (item.flags.includes("conflicting")) return "This instruction contradicts another instruction or the codebase";
  if (item.flags.includes("stale")) return "This instruction references files or systems that no longer exist";
  if (item.status === "supported") return `Assessor observed this instruction in ${item.metrics.sessionsObserved} of ${item.metrics.totalSessions} baseline traces`;
  return "No baseline trace exercised this instruction";
}

function Highlight({
  item,
  text,
  selected,
  decided,
  onSelect,
}: {
  item: ReviewItem;
  text: string;
  selected: boolean;
  decided: boolean;
  onSelect: (id: string, rect: DOMRect) => void;
}) {
  const ref = useRef<HTMLElement>(null);
  const handleClick = () => {
    if (ref.current) {
      onSelect(item.id, ref.current.getBoundingClientRect());
    }
  };
  const cls = ["hl", `hl-${item.verdict}`, selected && "selected", decided && "decided"]
    .filter(Boolean)
    .join(" ");
  return (
    <mark
      ref={ref}
      data-testid={`hl-${item.id}`}
      data-verdict={item.verdict}
      className={cls}
      onClick={handleClick}
    >
      {text}
      <span className="hl-tag" data-testid={`hl-tag-${item.id}`} tabIndex={0} data-tooltip={stateLabelTooltip(item)}>
        {stateLabel(item)}
      </span>
    </mark>
  );
}

const POPOVER_WIDTH = 360;
const GUTTER_GAP = 16;

function popoverStyle(rect: DOMRect, gutterLeft: number): React.CSSProperties {
  const left = gutterLeft + GUTTER_GAP;
  const available = window.innerWidth - left - 16;
  const fitsGutter = available >= 240;

  const actualLeft = fitsGutter
    ? left
    : Math.max(16, window.innerWidth - POPOVER_WIDTH - 16);
  const actualWidth = fitsGutter
    ? Math.min(POPOVER_WIDTH, available)
    : Math.min(POPOVER_WIDTH, window.innerWidth - 32);

  const top = Math.max(48, Math.min(rect.top - 12, window.innerHeight * 0.35));

  return {
    position: "fixed",
    top,
    left: actualLeft,
    width: actualWidth,
  };
}

function statusLabel(s: string): string {
  return s === "supported" ? "OBSERVED" : "UNOBSERVED";
}

function actionLabel(kind: string): string {
  if (kind === "update") return "Mark for update";
  if (kind === "remove") return "Mark for removal";
  return "Mark to add test";
}

function decidedLabel(kind: string): string {
  if (kind === "update") return "Marked for update";
  if (kind === "remove") return "Marked for removal";
  return "Marked to add test";
}

function Popover({
  item,
  anchorRect,
  gutterLeft,
  decision,
  onDecide,
  onClear,
  onSkip,
  onClose,
}: {
  item: ReviewItem;
  anchorRect: DOMRect;
  gutterLeft: number;
  decision: string | null;
  onDecide: (action: string) => void;
  onClear: () => void;
  onSkip: () => void;
  onClose: () => void;
}) {
  const pc = item.proposedChange;

  return (
    <div className="popover" data-testid="popover" style={popoverStyle(anchorRect, gutterLeft)}>
      <div className="po-top">
        <span className={`po-status ps-${item.status}`} tabIndex={0} data-tooltip={item.status === "supported" ? "Agent traces showed this instruction being followed" : "No agent trace exercised this instruction"}>
          {item.status === "supported" ? "●" : "○"} {statusLabel(item.status)}
        </span>
        <span className="po-chip" tabIndex={0} data-tooltip={stateLabelTooltip(item)}>{stateLabel(item)}</span>
        <button
          type="button"
          className="po-close"
          aria-label="Close"
          onClick={onClose}
        >
          ×
        </button>
      </div>

      <h3 className="po-title">{item.title}</h3>

      <div className="po-section">
        <span className="po-label">RECOMMENDATION</span>
        {pc ? (
          <>
            {pc.replacement && <pre className="po-code">{pc.replacement}</pre>}
            {pc.suggestedTest && <pre className="po-code">{pc.suggestedTest}</pre>}
            {pc.kind === "remove" && !pc.replacement && !pc.suggestedTest && (
              <p className="po-rec">Remove this instruction.</p>
            )}
            {decision ? (
              <div className="po-decided">
                <span className="po-decided-label">{decidedLabel(pc.kind)}</span>
                <button type="button" className="po-decided-clear" onClick={onClear}>
                  Undo
                </button>
              </div>
            ) : (
              <div className="po-actions">
                <button type="button" className={`po-btn pb-${pc.kind}`} onClick={() => onDecide(pc.kind)}>
                  {actionLabel(pc.kind)}
                </button>
                <button type="button" className="po-skip" onClick={onSkip}>
                  Skip
                </button>
              </div>
            )}
          </>
        ) : (
          <p className="po-rec">Keep as-is.</p>
        )}
      </div>

      <div className="po-section">
        <span className="po-label">WHY</span>
        <p className="po-why">{item.reason}</p>
      </div>

      {item.evidence.length > 0 && (
        <div className="po-section">
          <span className="po-label">EVIDENCE</span>
          {item.evidence.map((ev) => (
            <div key={ev.id} className={`po-ev${ev.kind === "ablation" ? " po-ev-ablation" : ""}`}>
              {ev.kind === "ablation" && <span className="po-ev-kind">ABLATION</span>}
              <p className="po-ev-text">{ev.excerpt}</p>
              <span className="po-ev-source">{ev.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function applyDecisions(source: string, items: ReviewItem[], decisions: Record<string, string>): string {
  const applied = items
    .filter((i) => i.id in decisions && i.proposedChange)
    .sort((a, b) => b.startOffset - a.startOffset);
  let result = source;
  for (const item of applied) {
    const kind = decisions[item.id];
    const pc = item.proposedChange!;
    if (kind === "remove") {
      let end = item.endOffset;
      while (end < result.length && (result[end] === "\n" || result[end] === "\r")) end++;
      result = result.slice(0, item.startOffset) + result.slice(end);
    } else if (kind === "update" && pc.replacement) {
      result = result.slice(0, item.startOffset) + pc.replacement + result.slice(item.endOffset);
    }
  }
  return result;
}

function summaryLine(kind: string, count: number): string | null {
  if (count === 0) return null;
  const n = count === 1 ? "1 instruction" : `${count} instructions`;
  if (kind === "remove") return `${n} removed`;
  if (kind === "update") return `${n} updated`;
  return `${n} with tests added`;
}

function Summary({
  review,
  source,
  decisions,
  skipped,
  reviewable,
  onBack,
}: {
  review: ReviewArtifact;
  source: string;
  decisions: Record<string, string>;
  skipped: Set<string>;
  reviewable: ReviewItem[];
  onBack: () => void;
}) {
  const [copied, setCopied] = useState(false);

  const grouped: Record<string, number> = {};
  for (const d of Object.values(decisions)) {
    grouped[d] = (grouped[d] ?? 0) + 1;
  }

  const handleCopy = () => {
    const patched = applyDecisions(source, reviewable, decisions);
    navigator.clipboard.writeText(patched).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const lines = ["remove", "update", "add_test"]
    .map((k) => summaryLine(k, grouped[k] ?? 0))
    .filter(Boolean);

  return (
    <div className="summary" data-testid="summary">
      <div className="summary-inner">
        <h2 className="summary-heading">Review Complete</h2>
        <p className="summary-sub">
          {review.source.repoName} / {review.source.contextPath}
        </p>

        {lines.length > 0 && (
          <div className="summary-impact">
            {lines.map((line, i) => (
              <span key={i} className="summary-impact-line">{line}</span>
            ))}
          </div>
        )}

        <div className="summary-changes">
          {reviewable.map((item) => {
            const d = decisions[item.id];
            const isSkipped = skipped.has(item.id);
            if (!d) return (
              <div key={item.id} className="sc-item sc-skipped">
                <div className="sc-head">
                  <span className="sc-title">{item.title}</span>
                  <span className="sc-action">{isSkipped ? "Skipped" : "Not reviewed"}</span>
                </div>
              </div>
            );
            const pc = item.proposedChange!;
            return (
              <div key={item.id} className="sc-item">
                <div className="sc-head">
                  <span className="sc-title">{item.title}</span>
                  <span className={`sc-action sc-${d}`}>{decidedLabel(d)}</span>
                </div>
                {d === "remove" && (
                  <pre className="sc-diff sc-removed">{item.snippet}</pre>
                )}
                {d === "update" && (
                  <>
                    <pre className="sc-diff sc-removed">{item.snippet}</pre>
                    <pre className="sc-diff sc-added">{pc.replacement}</pre>
                  </>
                )}
                {d === "add_test" && pc.suggestedTest && (
                  <pre className="sc-diff sc-added">{pc.suggestedTest}</pre>
                )}
              </div>
            );
          })}
        </div>

        <div className="summary-actions">
          <button type="button" className="rc-btn-primary rc-btn" onClick={handleCopy}>
            {copied ? "Copied!" : "Copy updated CLAUDE.md"}
          </button>
          <button type="button" className="rc-btn" onClick={onBack}>
            Back to review
          </button>
        </div>
      </div>
    </div>
  );
}
