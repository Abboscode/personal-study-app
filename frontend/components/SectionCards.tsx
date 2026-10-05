import Link from "next/link";

export type SectionSummary = {
  id: number;
  name: string;
  description: string | null;
  question_count: number;
  due_count: number;
};

export function SectionCards({ sections }: { sections: SectionSummary[] }) {
  if (sections.length === 0) {
    return (
      <section className="empty-state">
        <h2>No sections yet</h2>
        <p>Import questions to create the first section in this subject.</p>
        <Link className="secondary-button" href="/import">Import questions</Link>
      </section>
    );
  }

  return (
    <div className="section-grid">
      {sections.map((section) => (
        <article className="section-card" key={section.id}>
          <div>
            <p className="eyebrow">SECTION</p>
            <h2>{section.name}</h2>
            {section.description && <p className="section-description">{section.description}</p>}
          </div>
          <dl className="section-counts">
            <div>
              <dt>Questions</dt>
              <dd>{section.question_count}</dd>
            </div>
            <div>
              <dt>Due now</dt>
              <dd>{section.due_count}</dd>
            </div>
          </dl>
          <div className="card-actions">
            <Link className="primary-button" href={`/sections/${section.id}`}>
              Open section
            </Link>
            <button
              className="secondary-button"
              disabled
              title="Practice mode is not available yet"
              type="button"
            >
              Practice
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}

