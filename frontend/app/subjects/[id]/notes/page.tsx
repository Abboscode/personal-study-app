"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import type { StudyNote } from "@/app/notes/types";
import { NotesBrowser } from "@/components/NotesBrowser";

type Subject = { id: number; name: string };

export default function SubjectNotesPage() {
  const { id } = useParams<{ id: string }>();
  const [subject, setSubject] = useState<Subject | null>(null);
  const [notes, setNotes] = useState<StudyNote[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetch(`/api/subjects/${id}`, { signal: controller.signal }),
      fetch(`/api/subjects/${id}/notes`, { signal: controller.signal }),
    ])
      .then(async ([subjectResponse, notesResponse]) => {
        if (!subjectResponse.ok) throw new Error("Subject not found");
        if (!notesResponse.ok) throw new Error("Could not load notes");
        return Promise.all([subjectResponse.json(), notesResponse.json()]);
      })
      .then(([subjectData, notesData]) => { setSubject(subjectData); setNotes(notesData); })
      .catch((reason) => {
        if (reason instanceof Error && reason.name !== "AbortError") setError(reason.message);
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [id]);

  if (loading) return <div className="page-shell"><p className="muted">Loading notes…</p></div>;
  if (error || !subject) return <div className="narrow-shell"><p className="error">{error || "Subject not found"}</p></div>;

  return (
    <div className="page-shell hierarchy-page">
      <nav className="breadcrumbs" aria-label="Breadcrumb"><Link href="/">Dashboard</Link><span>/</span><Link href={`/subjects/${id}`}>{subject.name}</Link><span>/</span><span>Notes</span></nav>
      <header className="hierarchy-header">
        <div><p className="eyebrow">REFERENCE NOTES</p><h1>{subject.name}</h1><p>Concise lecture concepts, separate from spaced repetition.</p></div>
        <Link className="primary-button" href={`/notes/generate?subject_id=${id}`}>Generate notes</Link>
      </header>
      <NotesBrowser initialNotes={notes} />
    </div>
  );
}
