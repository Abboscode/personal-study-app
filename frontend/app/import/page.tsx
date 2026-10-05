"use client";

import { FormEvent, useState } from "react";

import { onlyJsonFiles } from "./importFiles";

type FileSummary = {
  filename: string;
  received: number;
  imported: number;
  duplicates: number;
  errors: string[];
};

type Summary = {
  files_received: number;
  files_processed: number;
  questions_received: number;
  questions_imported: number;
  duplicates: number;
  errors: number;
  files: FileSummary[];
};

export default function ImportPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [selectionMode, setSelectionMode] = useState<"single" | "folder" | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function selectFiles(selected: File[], mode: "single" | "folder") {
    setFiles(selected);
    setSelectionMode(mode);
    setSummary(null);
    setError("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (files.length === 0 || !selectionMode) return;
    setLoading(true);
    setError("");
    setSummary(null);
    const body = new FormData();
    const endpoint = selectionMode === "single" ? "/api/import" : "/api/import/batch";
    if (selectionMode === "single") body.append("file", files[0]);
    else files.forEach((file) => body.append("files", file, file.name));

    try {
      const response = await fetch(endpoint, { method: "POST", body });
      const result = await response.json();
      if (!response.ok) {
        const detail = typeof result.detail === "string" ? result.detail : JSON.stringify(result.detail);
        throw new Error(detail || "Import failed");
      }
      if (selectionMode === "single") {
        setSummary({
          files_received: 1,
          files_processed: 1,
          questions_received: result.received,
          questions_imported: result.imported,
          duplicates: result.duplicates,
          errors: result.errors,
          files: [
            {
              filename: files[0].name,
              received: result.received,
              imported: result.imported,
              duplicates: result.duplicates,
              errors: [],
            },
          ],
        });
      } else {
        setSummary(result);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Import failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="narrow-shell">
      <p className="eyebrow">ADD MATERIAL</p>
      <h1>Import questions</h1>
      <p className="lede">Upload one schema version 1.0 JSON file or import every JSON file in a folder. Existing external IDs are safely skipped.</p>

      <form className="import-card" onSubmit={submit}>
        <div className="import-options">
          <label className="file-picker compact-picker">
            <span>Select JSON file</span>
            <small>One question set</small>
            <input
              type="file"
              accept="application/json,.json"
              onChange={(event) => {
                const file = event.target.files?.[0];
                selectFiles(file ? [file] : [], "single");
                event.currentTarget.value = "";
              }}
            />
          </label>
          <label className="file-picker compact-picker">
            <span>Select folder</span>
            <small>All JSON files inside</small>
            <input
              type="file"
              accept="application/json,.json"
              multiple
              ref={(input) => {
                if (input) input.setAttribute("webkitdirectory", "");
              }}
              onChange={(event) => {
                selectFiles(onlyJsonFiles(event.target.files ?? []), "folder");
                event.currentTarget.value = "";
              }}
            />
          </label>
        </div>
        <div className="selection-summary" aria-live="polite">
          {files.length > 0 ? (
            <>
              <strong>Selected: {files.length} JSON {files.length === 1 ? "file" : "files"}</strong>
              {selectionMode === "single" && <span>{files[0].name}</span>}
            </>
          ) : (
            <span>No JSON files selected</span>
          )}
        </div>
        <button className="primary-button" disabled={files.length === 0 || loading} type="submit">
          {loading ? "Importing…" : selectionMode === "folder" ? "Import all" : "Import file"}
        </button>
      </form>

      {error && <div className="error" role="alert"><strong>Import failed.</strong> {error}</div>}
      {summary && (
        <section className="import-result" aria-live="polite">
          <h2>{summary.errors > 0 ? "Import completed with errors" : "Import complete"}</h2>
          <div className="result-grid">
            <div><strong>{summary.files_processed}</strong><span>Files processed</span></div>
            <div><strong>{summary.questions_received}</strong><span>Questions received</span></div>
            <div><strong>{summary.questions_imported}</strong><span>Imported</span></div>
            <div><strong>{summary.duplicates}</strong><span>Duplicates</span></div>
            <div><strong>{summary.errors}</strong><span>Errors</span></div>
          </div>
          <div className="file-results">
            {summary.files.map((file, index) => (
              <article className={file.errors.length > 0 ? "file-result has-errors" : "file-result"} key={`${file.filename}-${index}`}>
                <div>
                  <h3>{file.filename}</h3>
                  <p>{file.received} received · {file.imported} imported · {file.duplicates} duplicates</p>
                </div>
                {file.errors.length > 0 ? (
                  <ul>{file.errors.map((message) => <li key={message}>{message}</li>)}</ul>
                ) : (
                  <span className="file-status">Complete</span>
                )}
              </article>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
