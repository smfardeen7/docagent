import { useEffect, useRef, useState } from "react";
import { agentRun, query, type AgentResult, type QueryResult } from "../api";
import AnswerText from "./Citation";
import TraceView from "./TraceView";

type Mode = "rag" | "agent";
type Msg =
  | { role: "user"; text: string }
  | { role: "assistant"; mode: Mode; result: QueryResult | AgentResult };

function isAgent(r: QueryResult | AgentResult): r is AgentResult {
  return "steps" in r;
}

export default function ChatPanel() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [mode, setMode] = useState<Mode>("rag");
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!busy) return;
    const start = Date.now();
    setElapsed(0);
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 500);
    return () => clearInterval(t);
  }, [busy]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, busy]);

  async function submit() {
    const q = text.trim();
    if (!q || busy) return;
    setMsgs((m) => [...m, { role: "user", text: q }]);
    setText("");
    setError(null);
    setBusy(true);
    try {
      const result = mode === "rag" ? await query(q) : await agentRun(q);
      setMsgs((m) => [...m, { role: "assistant", mode, result }]);
    } catch (e) {
      const msg = (e as Error).message;
      setError(msg === "no documents indexed" ? "Upload a document first." : msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card chat">
      <div className="messages">
        {msgs.length === 0 && <p className="muted">Ask a question about your documents.</p>}
        {msgs.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="msg user">
              <div className="role">You</div>
              <div className="answer">{m.text}</div>
            </div>
          ) : (
            <div key={i} className="msg assistant">
              <div className="role">
                {m.mode === "agent" ? "Agent" : "RAG"}
                <span className="muted small"> · {(m.result.latency_ms / 1000).toFixed(1)}s</span>
              </div>
              <AnswerText text={m.result.answer} citations={m.result.citations} />
              {isAgent(m.result) && (
                <TraceView
                  steps={m.result.steps}
                  fallbackUsed={m.result.fallback_used}
                  parseFailures={m.result.parse_failures}
                />
              )}
            </div>
          ),
        )}
        {busy && <p className="muted">Thinking… {elapsed}s</p>}
        <div ref={endRef} />
      </div>
      {error && <p className="error">{error}</p>}
      <div className="composer">
        <textarea
          rows={3}
          value={text}
          disabled={busy}
          placeholder="Ask a question (Enter to send, Shift+Enter for newline)"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void submit();
            }
          }}
        />
        <div className="composer-row">
          <div className="toggle" role="group" aria-label="Mode">
            {(["rag", "agent"] as Mode[]).map((m) => (
              <button
                key={m}
                className={mode === m ? "active" : ""}
                disabled={busy}
                onClick={() => setMode(m)}
              >
                {m === "rag" ? "RAG" : "Agent"}
              </button>
            ))}
          </div>
          <button onClick={() => void submit()} disabled={busy || !text.trim()}>
            {busy ? `Working… ${elapsed}s` : "Send"}
          </button>
        </div>
      </div>
    </section>
  );
}
