"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import {
  SectionQuestionList,
  type SectionQuestion,
} from "@/components/SectionQuestionList";

import { deleteQuestionRequest, withoutQuestion } from "./questionDeletion";

type Section = {
  id: number;
  name: string;
  description: string | null;
  subject_id: number;
  subject_name: string;
  question_count: number;
  due_count: number;
  note_count: number;
};

export default function SectionPage() {
  const { id } = useParams<{ id: string }>();
  const [section, setSection] = useState<Section | null>(null);
  const [questions, setQuestions] = useState<SectionQuestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [deleteNotice, setDeleteNotice] = useState("");
  const [deletingQuestionIds, setDeletingQuestionIds] = useState<Set<number>>(
    () => new Set(),
  );

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");

    Promise.all([
      fetch(`/api/sections/${id}`, { signal: controller.signal }),
      fetch(`/api/sections/${id}/questions`, { signal: controller.signal }),
    ])
      .then(async ([sectionResponse, questionsResponse]) => {
        if (!sectionResponse.ok) throw new Error("Section not found");
        if (!questionsResponse.ok) throw new Error("Could not load this section’s questions");
        return Promise.all([sectionResponse.json(), questionsResponse.json()]);
      })
      .then(([sectionData, questionData]) => {
        setSection(sectionData);
        setQuestions(questionData);
      })
      .catch((reason) => {
        if (reason instanceof Error && reason.name !== "AbortError") setError(reason.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [id]);

  async function deleteQuestion(question: SectionQuestion) {
    setDeleteError("");
    setDeleteNotice("");
    setDeletingQuestionIds((current) => new Set(current).add(question.id));
    try {
      await deleteQuestionRequest(question.id);
      setQuestions((current) => withoutQuestion(current, question.id));
      setSection((current) => current && ({
        ...current,
        question_count: Math.max(0, current.question_count - 1),
        due_count: Math.max(0, current.due_count - (question.is_due ? 1 : 0)),
      }));
      setDeleteNotice("Question deleted.");
    } catch (reason) {
      setDeleteError(
        reason instanceof Error ? reason.message : "Could not delete the question",
      );
    } finally {
      setDeletingQuestionIds((current) => {
        const next = new Set(current);
        next.delete(question.id);
        return next;
      });
    }
  }

  if (loading) return <div className="page-shell"><p className="muted">Loading section…</p></div>;
  if (error || !section) {
    return (
      <div className="narrow-shell">
        <p className="error" role="alert">{error || "Section not found"}</p>
        <Link href="/">Back to dashboard</Link>
      </div>
    );
  }

  return (
    <div className="page-shell hierarchy-page">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link href="/">Dashboard</Link><span aria-hidden="true">/</span>
        <Link href={`/subjects/${section.subject_id}`}>{section.subject_name}</Link>
        <span aria-hidden="true">/</span><span>{section.name}</span>
      </nav>
      <header className="hierarchy-header section-header">
        <div>
          <p className="eyebrow">SECTION</p>
          <p className="parent-subject">{section.subject_name}</p>
          <h1>{section.name}</h1>
          {section.description && <p>{section.description}</p>}
        </div>
        <div className="section-header-side">
          <dl className="header-counts">
            <div><dt>Questions</dt><dd>{section.question_count}</dd></div>
            <div><dt>Due now</dt><dd>{section.due_count}</dd></div>
            <div><dt>Notes</dt><dd>{section.note_count}</dd></div>
          </dl>
          <button
            className="primary-button"
            disabled
            title="Practice mode is not available yet"
            type="button"
          >
            Practice section
          </button>
          <Link className="secondary-button" href={`/sections/${id}/notes`}>Browse notes</Link>
        </div>
      </header>

      <div className="list-heading">
        <div><p className="eyebrow">QUESTION BANK</p><h2>Questions</h2></div>
        <span>{questions.length} total</span>
      </div>
      {deleteError && <p className="error" role="alert">{deleteError}</p>}
      {deleteNotice && <p className="success-notice" role="status">{deleteNotice}</p>}
      <SectionQuestionList
        deletingQuestionIds={deletingQuestionIds}
        onDeleteQuestion={(question) => void deleteQuestion(question)}
        questions={questions}
      />
    </div>
  );
}
