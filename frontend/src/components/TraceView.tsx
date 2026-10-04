import { useState } from "react";
import type { Step } from "../api";

function Observation({ text }: { text: string }) {
  const [full, setFull] = useState(false);
  const long = text.length > 600;
  return (
    <>
      <pre className="mono">{long && !full ? text.slice(0, 600) + "…" : text}</pre>
      {long && (
        <button className="link" onClick={() => setFull(!full)}>
          {full ? "show less" : "show more"}
        </button>
      )}
    </>
  );
}

export default function TraceView({
  steps,
  fallbackUsed,
  parseFailures,
}: {
  steps: Step[];
  fallbackUsed: boolean;
  parseFailures: number;
}) {
  return (
    <details className="trace">
      <summary>
        Agent trace ({steps.length} steps)
        {fallbackUsed && <span className="badge fallback">fell back to RAG</span>}
        {parseFailures > 0 && <span className="muted small"> · {parseFailures} parse failures</span>}
      </summary>
      <ol>
        {steps.map((s) => (
          <li key={s.n}>
            <div>
              <strong>Step {s.n}</strong> <span className="chip">{s.tool}</span>
            </div>
            {s.thought && <p className="muted small">{s.thought}</p>}
            <pre className="mono">{JSON.stringify(s.args, null, 2)}</pre>
            <Observation text={s.observation} />
          </li>
        ))}
      </ol>
    </details>
  );
}
