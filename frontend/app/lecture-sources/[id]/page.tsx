"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

type LectureSourceDetail = {
  id: number;
  subject_id: number;
  subject_name: string;
  original_filename: string;
  page_count: number | null;
  uploaded_at: string;
  question_count: number;
  note_count: number;
  section_count: number;
  file_url: string;
  sections: Array<{ id: number; name: string; question_count: number }>;
  note_sections: Array<{ id: number; name: string; note_count: number }>;
};

export default function LectureSourcePage() {
  const { id } = useParams<{ id: string }>();
  const [source, setSource] = useState<LectureSourceDetail | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`/api/lecture-sources/${id}`, {
      cache: "no-store",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("Lecture source not found");
        return response.json();
      })
      .then(setSource)
      .catch((reason) => {
        if (reason instanceof Error && reason.name !== "AbortError") {
          setError(reason.message);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [id]);

  if (loading) return <div className="page-shell"><p className="muted">Loading lecture material…</p></div>;
  if (error || !source) return <div className="narrow-shell"><p className="error">{error || "Lecture source not found"}</p></div>;

  return (
    <div className="page-shell hierarchy-page">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link href="/">Dashboard</Link><span aria-hidden="true">/</span>
        <Link href={`/subjects/${source.subject_id}`}>{source.subject_name}</Link>
        <span aria-hidden="true">/</span><span>{source.original_filename}</span>
      </nav>
      <header className="hierarchy-header lecture-detail-header">
        <div>
          <p className="eyebrow">LECTURE MATERIAL</p>
          <h1>{source.original_filename}</h1>
          <p>Uploaded {new Date(source.uploaded_at).toLocaleDateString()}</p>
        </div>
        <div className="section-header-side">
          <dl className="header-counts">
            <div><dt>Pages</dt><dd>{source.page_count ?? "—"}</dd></div>
            <div><dt>Questions</dt><dd>{source.question_count}</dd></div>
            <div><dt>Notes</dt><dd>{source.note_count}</dd></div>
            <div><dt>Sections</dt><dd>{source.section_count}</dd></div>
          </dl>
          <div className="lecture-actions">
            <Link className="primary-button" href={`/notes/generate?subject_id=${source.subject_id}&source_id=${source.id}`}>Generate notes</Link>
            <a className="secondary-button" href={source.file_url} rel="noreferrer" target="_blank">Open PDF</a>
          </div>
        </div>
      </header>

      <div className="list-heading">
        <div><p className="eyebrow">GENERATED CONTENT</p><h2>Sections</h2></div>
      </div>
      {source.sections.length === 0 ? (
        <section className="empty-state"><h3>No linked questions yet</h3><p>This PDF has been saved, but its generated questions have not been imported.</p></section>
      ) : (
        <div className="source-section-list">
          {source.sections.map((section) => (
            <Link href={`/sections/${section.id}`} key={section.id}>
              <span>{section.name}</span>
              <small>{section.question_count} {section.question_count === 1 ? "question" : "questions"}</small>
            </Link>
          ))}
        </div>
      )}
      <div className="list-heading"><div><p className="eyebrow">REFERENCE MATERIAL</p><h2>Notes</h2></div><span>{source.note_count} total</span></div>
      {source.note_sections.length === 0 ? <section className="empty-state compact-empty-state"><h3>No notes yet</h3><p>Generate concise reference notes from this lecture.</p><Link className="secondary-button" href={`/notes/generate?subject_id=${source.subject_id}&source_id=${source.id}`}>Generate notes</Link></section> : <div className="source-section-list">{source.note_sections.map((section) => <Link href={`/sections/${section.id}/notes`} key={section.id}><span>{section.name}</span><small>{section.note_count} {section.note_count === 1 ? "note" : "notes"}</small></Link>)}</div>}
    </div>
  );
}
