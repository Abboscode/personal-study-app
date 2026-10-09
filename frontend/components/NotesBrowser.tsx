"use client";

import { FormEvent, useMemo, useState } from "react";

import type { NoteType, StudyNote } from "@/app/notes/types";

import { Markdown } from "./Markdown";
import { SourceReference } from "./SourceReference";

const NOTE_TYPES: NoteType[] = ["formula", "theorem", "concept", "procedure"];

type EditDraft = {
  note_type: NoteType;
  title: string;
  content_markdown: string;
  source_page: string;
};

async function responseMessage(response: Response, fallback: string): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object") {
      const detail = (body as Record<string, unknown>).detail;
      if (typeof detail === "string") return detail;
    }
  } catch {
    // Keep the caller's safe fallback.
  }
  return fallback;
}

export function NotesBrowser({ initialNotes }: { initialNotes: StudyNote[] }) {
  const [notes, setNotes] = useState(initialNotes);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState<EditDraft | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const grouped = useMemo(() => {
    const groups = new Map<string, StudyNote[]>();
    for (const note of notes) {
      const group = groups.get(note.section_name) ?? [];
      group.push(note);
      groups.set(note.section_name, group);
    }
    return [...groups.entries()];
  }, [notes]);

  function beginEdit(note: StudyNote) {
    setError("");
    setEditingId(note.id);
    setDraft({
      note_type: note.note_type,
      title: note.title,
      content_markdown: note.content_markdown,
      source_page: note.source_page ?? "",
    });
  }

  async function saveEdit(event: FormEvent, note: StudyNote) {
    event.preventDefault();
    if (!draft) return;
    setBusyId(note.id);
    setError("");
    try {
      const response = await fetch(`/api/notes/${note.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...draft,
          source_page: draft.source_page.trim() || null,
        }),
      });
      if (!response.ok) throw new Error(await responseMessage(response, "Could not update note"));
      const updated: StudyNote = await response.json();
      setNotes((current) => current.map((item) => item.id === note.id ? updated : item));
      setEditingId(null);
      setDraft(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not update note");
    } finally {
      setBusyId(null);
    }
  }

  async function removeNote(note: StudyNote) {
    if (!window.confirm(`Delete “${note.title}”? This permanently removes the note.`)) return;
    setBusyId(note.id);
    setError("");
    try {
      const response = await fetch(`/api/notes/${note.id}`, { method: "DELETE" });
      if (!response.ok) throw new Error(await responseMessage(response, "Could not delete note"));
      setNotes((current) => current.filter((item) => item.id !== note.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not delete note");
    } finally {
      setBusyId(null);
    }
  }

  if (notes.length === 0) {
    return <section className="empty-state"><h2>No notes yet</h2><p>Generate concise notes from a saved lecture or a new PDF.</p></section>;
  }

  return (
    <div className="notes-browser">
      {error && <p className="error" role="alert">{error}</p>}
      {grouped.map(([sectionName, sectionNotes]) => (
        <section className="notes-section" key={sectionName}>
          <header><h2>{sectionName}</h2><span>{sectionNotes.length} notes</span></header>
          <div className="note-card-grid">
            {sectionNotes.map((note) => (
              <article className="note-card" key={note.id}>
                {editingId === note.id && draft ? (
                  <form className="note-edit-form" onSubmit={(event) => void saveEdit(event, note)}>
                    <label><span>Title</span><input required value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label>
                    <label><span>Type</span><select value={draft.note_type} onChange={(event) => setDraft({ ...draft, note_type: event.target.value as NoteType })}>{NOTE_TYPES.map((type) => <option key={type}>{type}</option>)}</select></label>
                    <label><span>Source page</span><input value={draft.source_page} onChange={(event) => setDraft({ ...draft, source_page: event.target.value })} /></label>
                    <label><span>Markdown content</span><textarea required rows={12} value={draft.content_markdown} onChange={(event) => setDraft({ ...draft, content_markdown: event.target.value })} /></label>
                    <div className="note-actions"><button className="primary-button" disabled={busyId === note.id} type="submit">Save</button><button className="secondary-button" onClick={() => { setEditingId(null); setDraft(null); }} type="button">Cancel</button></div>
                  </form>
                ) : (
                  <details>
                    <summary>
                      <span><strong>{note.title}</strong><small>{note.note_type}</small></span>
                      {note.source_page && <small>Page {note.source_page}</small>}
                    </summary>
                    <div className="note-card-body">
                      <Markdown>{note.content_markdown}</Markdown>
                      <SourceReference sourceDocument={note.source_document} sourcePage={note.source_page} />
                      <div className="note-actions">
                        <button className="secondary-button" onClick={() => beginEdit(note)} type="button">Edit</button>
                        <button className="question-delete-button" disabled={busyId === note.id} onClick={() => void removeNote(note)} type="button">{busyId === note.id ? "Deleting…" : "Delete"}</button>
                      </div>
                    </div>
                  </details>
                )}
              </article>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
