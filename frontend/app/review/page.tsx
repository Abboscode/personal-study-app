"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Markdown } from "@/components/Markdown";
import { SourceDocumentReference, SourceReference } from "@/components/SourceReference";

type Rating = "again" | "hard" | "good" | "easy";
type DueQuestion = {
  id: number;
  subject: string;
  section: string;
  question_type: string;
  question: string;
  answer: string;
  tags: string[];
  source: string | null;
  source_page: string | null;
  source_document: SourceDocumentReference | null;
};

export default function ReviewPage() {
  const [queue, setQueue] = useState<DueQuestion[]>([]);
  const [revealed, setRevealed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [rating, setRating] = useState(false);
  const [error, setError] = useState("");
  const [completed, setCompleted] = useState(0);

  const loadQueue = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/review/due?limit=100", { cache: "no-store" });
      if (!response.ok) throw new Error("Could not load due questions");
      setQueue(await response.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load due questions");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadQueue(); }, [loadQueue]);

  async function submitRating(value: Rating) {
    const current = queue[0];
    if (!current || rating) return;
    setRating(true);
    setError("");
    try {
      const response = await fetch(`/api/review/${current.id}/rate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rating: value }),
      });
      if (!response.ok) throw new Error("The rating could not be saved");
      setQueue((items) => items.slice(1));
      setCompleted((count) => count + 1);
      setRevealed(false);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The rating could not be saved");
    } finally {
      setRating(false);
    }
  }

  if (loading) return <div className="review-shell"><p className="muted">Preparing your review…</p></div>;
  if (error && queue.length === 0) return <div className="review-shell"><p className="error">{error}</p></div>;

  const current = queue[0];
  if (!current) {
    return (
      <div className="review-shell complete-state">
        <div className="completion-mark">✓</div>
        <p className="eyebrow">SESSION COMPLETE</p>
        <h1>You’re caught up.</h1>
        <p>{completed ? `You reviewed ${completed} ${completed === 1 ? "question" : "questions"}.` : "There are no questions due right now."}</p>
        <Link className="secondary-button" href="/">Back to dashboard</Link>
      </div>
    );
  }

  return (
    <div className="review-shell">
      <div className="review-progress">
        <span>{completed} completed</span>
        <span>{queue.length} remaining</span>
      </div>
      <article className="review-card">
        <header>
          <p>{current.subject}</p>
          <span>{current.section}</span>
        </header>
        <div className="review-content">
          <div className="question-meta">
            <span>{current.question_type}</span>
            {current.tags.slice(0, 3).map((tag) => <span key={tag}>#{tag}</span>)}
          </div>
          <section aria-label="Question">
            <p className="card-label">Question</p>
            <Markdown>{current.question}</Markdown>
          </section>
          <SourceReference
            compact
            sourceDocument={current.source_document}
            sourcePage={current.source_page}
            sourceText={current.source}
          />

          {!revealed ? (
            <button className="show-answer" onClick={() => setRevealed(true)}>Show answer</button>
          ) : (
            <>
              <section className="answer" aria-label="Answer">
                <p className="card-label">Answer</p>
                <Markdown>{current.answer}</Markdown>
              </section>
              {error && <p className="error" role="alert">{error}</p>}
              <div className="ratings" aria-label="Rate your answer">
                <button disabled={rating} className="again" onClick={() => submitRating("again")}><strong>Again</strong><span>Forgot</span></button>
                <button disabled={rating} className="hard" onClick={() => submitRating("hard")}><strong>Hard</strong><span>Difficult</span></button>
                <button disabled={rating} className="good" onClick={() => submitRating("good")}><strong>Good</strong><span>Recalled</span></button>
                <button disabled={rating} className="easy" onClick={() => submitRating("easy")}><strong>Easy</strong><span>Effortless</span></button>
              </div>
            </>
          )}
        </div>
      </article>
    </div>
  );
}
