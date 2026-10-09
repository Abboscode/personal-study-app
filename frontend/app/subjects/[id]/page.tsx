"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { SectionCards, type SectionSummary } from "@/components/SectionCards";
import {
  LectureSourceCards,
  type LectureSourceSummary,
} from "@/components/LectureSourceCards";

type Subject = {
  id: number;
  name: string;
  description: string | null;
  note_count: number;
};

export default function SubjectPage() {
  const { id } = useParams<{ id: string }>();
  const [subject, setSubject] = useState<Subject | null>(null);
  const [sections, setSections] = useState<SectionSummary[]>([]);
  const [lectureSources, setLectureSources] = useState<LectureSourceSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");

    Promise.all([
      fetch(`/api/subjects/${id}`, { signal: controller.signal }),
      fetch(`/api/subjects/${id}/sections`, { signal: controller.signal }),
      fetch(`/api/subjects/${id}/lecture-sources`, { signal: controller.signal }),
    ])
      .then(async ([subjectResponse, sectionsResponse, sourcesResponse]) => {
        if (!subjectResponse.ok) throw new Error("Subject not found");
        if (!sectionsResponse.ok) throw new Error("Could not load this subject’s sections");
        if (!sourcesResponse.ok) throw new Error("Could not load this subject’s lecture materials");
        return Promise.all([
          subjectResponse.json(),
          sectionsResponse.json(),
          sourcesResponse.json(),
        ]);
      })
      .then(([subjectData, sectionData, sourceData]) => {
        setSubject(subjectData);
        setSections(sectionData);
        setLectureSources(sourceData);
      })
      .catch((reason) => {
        if (reason instanceof Error && reason.name !== "AbortError") setError(reason.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [id]);

  if (loading) return <div className="page-shell"><p className="muted">Loading subject…</p></div>;
  if (error || !subject) {
    return (
      <div className="narrow-shell">
        <p className="error" role="alert">{error || "Subject not found"}</p>
        <Link href="/">Back to dashboard</Link>
      </div>
    );
  }

  const questionCount = sections.reduce((total, section) => total + section.question_count, 0);
  const dueCount = sections.reduce((total, section) => total + section.due_count, 0);

  return (
    <div className="page-shell hierarchy-page">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link href="/">Dashboard</Link><span aria-hidden="true">/</span><span>{subject.name}</span>
      </nav>
      <header className="hierarchy-header">
        <div>
          <p className="eyebrow">SUBJECT</p>
          <h1>{subject.name}</h1>
          {subject.description && <p>{subject.description}</p>}
        </div>
        <dl className="header-counts">
          <div><dt>Sections</dt><dd>{sections.length}</dd></div>
          <div><dt>Questions</dt><dd>{questionCount}</dd></div>
          <div><dt>Due now</dt><dd>{dueCount}</dd></div>
          <div><dt>Notes</dt><dd>{subject.note_count}</dd></div>
        </dl>
      </header>
      <div className="list-heading">
        <div><p className="eyebrow">CHAPTERS</p><h2>Sections</h2></div>
      </div>
      <SectionCards sections={sections} />
      <div className="subject-note-actions"><Link className="secondary-button" href={`/subjects/${id}/notes`}>Browse notes</Link><Link className="primary-button" href={`/notes/generate?subject_id=${id}`}>Generate notes</Link></div>
      <div className="list-heading lecture-heading">
        <div><p className="eyebrow">SOURCE LIBRARY</p><h2>Lecture materials</h2></div>
        <span>{lectureSources.length} total</span>
      </div>
      <LectureSourceCards sources={lectureSources} />
    </div>
  );
}
