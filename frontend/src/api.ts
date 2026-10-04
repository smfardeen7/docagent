const BASE = import.meta.env.VITE_API_BASE ?? "/api";

export type DocStatus = "queued" | "processing" | "ready" | "failed";
export interface Doc {
  id: string;
  filename: string;
  status: DocStatus;
  reason: string | null;
  n_chunks: number;
  created_at: string;
}
export interface CitationT {
  n: number;
  chunk_id: number;
  doc_id: string;
  ordinal: number;
  text: string;
}
export interface Step {
  n: number;
  thought: string;
  tool: string;
  args: Record<string, unknown>;
  observation: string;
}
export interface QueryResult {
  answer: string;
  citations: CitationT[];
  run_id: string;
  latency_ms: number;
}
export interface AgentResult extends QueryResult {
  steps: Step[];
  fallback_used: boolean;
  parse_failures: number;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, init);
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") msg = body.detail;
      else if (body.detail) msg = JSON.stringify(body.detail);
    } catch {
      /* non-JSON body */
    }
    throw new Error(msg);
  }
  return (await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const listDocuments = () => request<Doc[]>("/documents");

export function uploadDocument(file: File) {
  const form = new FormData();
  form.append("file", file);
  return request<{ doc_id: string; status: DocStatus }>("/documents", {
    method: "POST",
    body: form,
  });
}

export const query = (question: string, topK?: number) =>
  request<QueryResult>("/query", json({ question, top_k: topK }));

export const agentRun = (question: string, maxSteps?: number) =>
  request<AgentResult>("/agent/run", json({ question, max_steps: maxSteps }));
