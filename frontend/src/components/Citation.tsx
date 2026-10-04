import { useState } from "react";
import type { CitationT } from "../api";

export default function AnswerText({ text, citations }: { text: string; citations: CitationT[] }) {
  const [open, setOpen] = useState<number | null>(null);
  const byN = new Map(citations.map((c) => [c.n, c]));
  const parts = text.split(/(\[\d+\])/g);
  const active = open !== null ? byN.get(open) : undefined;

  return (
    <div>
      <div className="answer">
        {parts.map((p, i) => {
          const m = /^\[(\d+)\]$/.exec(p);
          if (m) {
            const n = Number(m[1]);
            if (byN.has(n)) {
              return (
                <button
                  key={i}
                  className={`cite${open === n ? " on" : ""}`}
                  onClick={() => setOpen(open === n ? null : n)}
                >
                  {n}
                </button>
              );
            }
          }
          return <span key={i}>{p}</span>;
        })}
      </div>
      {active && (
        <div className="cite-panel">
          <div className="muted small">
            [{active.n}] doc {active.doc_id} · chunk #{active.ordinal}
          </div>
          <div>{active.text}</div>
        </div>
      )}
    </div>
  );
}
