"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Markdown } from "@/components/Markdown";

type Section = {
  id: number;
  name: string;
  description: string | null;
  subject_id: number;
  subject_name: string;
  question_count: number;
  due_count: number;
};

type Question = {
  id: number;
  external_id: string;
  question_type: string;
  question: string;
  difficulty_level: number;
  tags: string[];
  is_due: boolean;
};

export default function SectionPage() {
  const { id } = useParams<{ id: string }>();
  const [section, setSection] = useState<Section | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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
          </dl>
          <button
            className="primary-button"
            disabled
            title="Practice mode is not available yet"
            type="button"
          >
            Practice section
          </button>
        </div>
      </header>

      <div className="list-heading">
        <div><p className="eyebrow">QUESTION BANK</p><h2>Questions</h2></div>
        <span>{questions.length} total</span>
      </div>
      {questions.length === 0 ? (
        <section className="empty-state"><h2>No questions yet</h2></section>
      ) : (
        <ol className="question-list">
          {questions.map((question) => (
            <li className="question-list-item" key={question.id}>
              <div className="question-list-meta">
                <span>{question.question_type}</span>
                <span>Difficulty {question.difficulty_level}</span>
                {question.is_due && <span className="due-badge">Due</span>}
              </div>
              <Markdown>{question.question}</Markdown>
              {question.tags.length > 0 && (
                <div className="tag-list">
                  {question.tags.map((tag) => <span key={tag}>#{tag}</span>)}
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

