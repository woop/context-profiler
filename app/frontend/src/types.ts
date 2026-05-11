export type Verdict = "keep" | "update" | "remove" | "add_test";
export type Status = "supported" | "unobserved";
export type Flag = "conflicting" | "stale";

export interface Evidence {
  id: string;
  kind: "trace" | "absence" | "conflict" | "ablation";
  context_variant: string;
  label: string;
  source: string;
  excerpt: string;
  explanation: string;
}

export interface ProposedChange {
  kind: "update" | "remove" | "add_test";
  rationale: string;
  replacement?: string;
  suggestedTest?: string;
}

export interface ReviewItem {
  id: string;
  verdict: Verdict;
  status: Status;
  flags: Flag[];
  title: string;
  snippet: string;
  sourceFile: string;
  startOffset: number;
  endOffset: number;
  tokenCount: number;
  tokenDelta: number;
  metrics: {
    sessionsObserved: number;
    totalSessions: number;
    traceEvents: number;
  };
  reason: string;
  evidence: Evidence[];
  proposedChange?: ProposedChange;
}

export interface ReviewArtifact {
  version: 1;
  source: {
    repoName: string;
    contextPath: string;
    contextHash: string;
    generatedAt: string;
  };
  summary: {
    totalInstructions: number;
    totalRuns: number;
    verdictCounts: Record<Verdict, number>;
    statusCounts: Record<Status, number>;
    flagCounts: Record<Flag, number>;
    estimatedTokenChange: number;
  };
  items: ReviewItem[];
}

export interface SourceArtifact {
  repoName: string;
  contextPath: string;
  contextHash: string;
  text: string;
}
