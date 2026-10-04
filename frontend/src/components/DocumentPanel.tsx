import { useCallback, useEffect, useRef, useState } from "react";
import { listDocuments, uploadDocument, type Doc } from "../api";

export default function DocumentPanel() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      setDocs(await listDocuments());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const active = docs.some((d) => d.status === "queued" || d.status === "processing");
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => void refresh(), 3000);
    return () => clearInterval(t);
  }, [active, refresh]);

  async function onUpload() {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await uploadDocument(file);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
    }
  }

  return (
    <section className="card">
      <h2>Documents</h2>
      <div className="upload">
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.md,.markdown,.txt"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <button onClick={onUpload} disabled={!file || uploading}>
          {uploading ? "Uploading…" : "Upload"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {docs.length === 0 && !error && <p className="muted">No documents yet.</p>}
      <ul className="docs">
        {docs.map((d) => (
          <li key={d.id}>
            <div className="doc-row">
              <span className="doc-name" title={d.filename}>{d.filename}</span>
              <span className={`badge ${d.status}`}>{d.status}</span>
            </div>
            <div className="muted small">
              {d.n_chunks} chunks
              {d.status === "failed" && d.reason ? ` · ${d.reason}` : ""}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
