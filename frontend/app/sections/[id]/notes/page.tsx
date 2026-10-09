"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import type { StudyNote } from "@/app/notes/types";
import { NotesBrowser } from "@/components/NotesBrowser";

type Section = { id: number; name: string; subject_id: number; subject_name: string };

export default function SectionNotesPage() {
  const { id } = useParams<{ id: string }>();
  const [section, setSection] = useState<Section | null>(null);
  const [notes, setNotes] = useState<StudyNote[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetch(`/api/sections/${id}`, { signal: controller.signal }),
      fetch(`/api/sections/${id}/notes`, { signal: controller.signal }),
    ])
      .then(async ([sectionResponse, notesResponse]) => {
        if (!sectionResponse.ok) throw new Error("Section not found");
        if (!notesResponse.ok) throw new Error("Could not load notes");
        return Promise.all([sectionResponse.json(), notesResponse.json()]);
      })
      .then(([sectionData, notesData]) => { setSection(sectionData); setNotes(notesData); })
      .catch((reason) => {
        if (reason instanceof Error && reason.name !== "AbortError") setError(reason.message);
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [id]);

  if (loading) return <div className="page-shell"><p className="muted">Loading notes…</p></div>;
  if (error || !section) return <div className="narrow-shell"><p className="error">{error || "Section not found"}</p></div>;

  return (
    <div className="page-shell hierarchy-page">
      <nav className="breadcrumbs" aria-label="Breadcrumb"><Link href="/">Dashboard</Link><span>/</span><Link href={`/subjects/${section.subject_id}`}>{section.subject_name}</Link><span>/</span><Link href={`/sections/${id}`}>{section.name}</Link><span>/</span><span>Notes</span></nav>
      <header className="hierarchy-header">
        <div><p className="eyebrow">SECTION NOTES</p><h1>{section.name}</h1><p>{section.subject_name}</p></div>
        <Link className="primary-button" href={`/notes/generate?subject_id=${section.subject_id}&section_name=${encodeURIComponent(section.name)}`}>Generate notes</Link>
      </header>
      <NotesBrowser initialNotes={notes} />
    </div>
  );
}
