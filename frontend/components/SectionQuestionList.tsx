"use client";

import { useState } from "react";

import { Markdown } from "./Markdown";
import { SourceDocumentReference, SourceReference } from "./SourceReference";

export type SectionQuestion = {
  id: number;
  external_id: string;
  question_type: string;
  question: string;
  answer: string;
  difficulty_level: number;
  tags: string[];
  is_due: boolean;
  source?: string | null;
  source_page?: string | null;
  source_document?: SourceDocumentReference | null;
};

export function toggleExpandedQuestion(
  expandedQuestions: ReadonlySet<number>,
  questionId: number,
): Set<number> {
  const next = new Set(expandedQuestions);
  if (next.has(questionId)) next.delete(questionId);
  else next.add(questionId);
  return next;
}

export function SectionQuestionList({
  questions,
  initiallyExpandedQuestionIds = [],
  deletingQuestionIds = new Set<number>(),
  onDeleteQuestion,
}: {
  questions: SectionQuestion[];
  initiallyExpandedQuestionIds?: readonly number[];
  deletingQuestionIds?: ReadonlySet<number>;
  onDeleteQuestion?: (question: SectionQuestion) => void;
}) {
  const [expandedQuestions, setExpandedQuestions] = useState(
    () => new Set(initiallyExpandedQuestionIds),
  );

  if (questions.length === 0) {
    return <section className="empty-state"><h2>No questions yet</h2></section>;
  }

  return (
    <ol className="question-list">
      {questions.map((question, index) => {
        const expanded = expandedQuestions.has(question.id);
        const deleting = deletingQuestionIds.has(question.id);
        const answerId = `section-question-answer-${question.id}`;

        return (
          <li className="question-list-item" key={question.id}>
            <p className="question-number">Question {index + 1}</p>
            <div className="question-list-meta">
              <span>{question.question_type}</span>
              <span>Difficulty {question.difficulty_level}</span>
              {question.is_due && <span className="due-badge">Due</span>}
            </div>
            <Markdown>{question.question}</Markdown>
            <SourceReference
              sourceDocument={question.source_document}
              sourcePage={question.source_page}
              sourceText={question.source}
            />

            {expanded && (
              <section className="question-list-answer" id={answerId} aria-label={`Answer to question ${index + 1}`}>
                <p className="card-label">Answer</p>
                <Markdown>{question.answer}</Markdown>
              </section>
            )}

            <div className="question-card-actions">
              <button
                aria-controls={answerId}
                aria-expanded={expanded}
                className="question-answer-toggle"
                onClick={() => {
                  setExpandedQuestions((current) => toggleExpandedQuestion(current, question.id));
                }}
                type="button"
              >
                {expanded ? "Hide answer" : "Show answer"}
              </button>

              {onDeleteQuestion && (
                <button
                  aria-label={`Delete question ${index + 1}`}
                  className="question-delete-button"
                  disabled={deleting}
                  onClick={() => {
                    const confirmed = window.confirm(
                      `Delete Question ${index + 1}? This permanently removes the question and its review history.`,
                    );
                    if (confirmed) onDeleteQuestion(question);
                  }}
                  type="button"
                >
                  {deleting ? "Deleting…" : "Delete question"}
                </button>
              )}
            </div>

            {question.tags.length > 0 && (
              <div className="tag-list">
                {question.tags.map((tag) => <span key={tag}>#{tag}</span>)}
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
