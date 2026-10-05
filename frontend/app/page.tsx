"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type Subject = {
  id: number;
  name: string;
  section_count: number;
  question_count: number;
  due_count: number;
};

type Dashboard = {
  due_today: number;
  new_questions: number;
  reviewed_today: number;
  subjects: Subject[];
};

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/dashboard")
      .then(async (response) => {
        if (!response.ok) throw new Error("Could not load the dashboard");
        return response.json();
      })
      .then(setData)
      .catch((reason) => setError(reason.message));
  }, []);

  return (
    <div className="page-shell">
      <section className="hero">
        <p className="eyebrow">YOUR STUDY DESK</p>
        <h1>What will you remember today?</h1>
        <p>Work through what is due, one thoughtful answer at a time.</p>
        <Link className="primary-button" href="/review">Start review</Link>
      </section>

      {error && <p className="error" role="alert">{error}</p>}
      {!data && !error && <p className="muted">Loading your study plan…</p>}
      {data && (
        <>
          <section className="stats" aria-label="Study statistics">
            <article><span>Due now</span><strong>{data.due_today}</strong></article>
            <article><span>New questions</span><strong>{data.new_questions}</strong></article>
            <article><span>Reviewed today</span><strong>{data.reviewed_today}</strong></article>
          </section>

          <section className="section-heading">
            <div>
              <p className="eyebrow">LIBRARY</p>
              <h2>Subjects</h2>
            </div>
            <Link href="/import">Import questions</Link>
          </section>

          {data.subjects.length === 0 ? (
            <section className="empty-state">
              <h3>Your library is ready</h3>
              <p>Import a question set to create your first subject and section.</p>
              <Link className="secondary-button" href="/import">Import JSON</Link>
            </section>
          ) : (
            <div className="subject-grid">
              {data.subjects.map((subject) => (
                <article className="subject-card" key={subject.id}>
                  <div className="subject-accent" />
                  <h3>{subject.name}</h3>
                  <p>{subject.section_count} {subject.section_count === 1 ? "section" : "sections"} · {subject.question_count} questions</p>
                  <div className="due-line"><strong>{subject.due_count}</strong><span>due now</span></div>
                  <Link href={`/subjects/${subject.id}`}>Open subject <span aria-hidden="true">→</span></Link>
                </article>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
