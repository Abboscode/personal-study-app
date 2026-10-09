import Link from "next/link";

export type LectureSourceSummary = {
  id: number;
  subject_id: number;
  original_filename: string;
  page_count: number | null;
  uploaded_at: string;
  question_count: number;
  note_count: number;
  section_count: number;
  file_url: string;
};

export function LectureSourceCards({
  sources,
}: {
  sources: LectureSourceSummary[];
}) {
  if (sources.length === 0) {
    return (
      <section className="empty-state compact-empty-state">
        <h3>No lecture materials yet</h3>
        <p>PDFs used for AI question generation will appear here.</p>
        <Link className="secondary-button" href="/generate">
          Generate from PDF
        </Link>
      </section>
    );
  }

  return (
    <div className="lecture-source-grid">
      {sources.map((source) => (
        <Link
          className="lecture-source-card"
          href={`/lecture-sources/${source.id}`}
          key={source.id}
        >
          <div>
            <p className="eyebrow">LECTURE PDF</p>
            <h3>{source.original_filename}</h3>
            {source.page_count != null && <p>{source.page_count} pages</p>}
          </div>
          <dl>
            <div><dt>Questions</dt><dd>{source.question_count}</dd></div>
            <div><dt>Notes</dt><dd>{source.note_count}</dd></div>
            <div><dt>Sections</dt><dd>{source.section_count}</dd></div>
          </dl>
        </Link>
      ))}
    </div>
  );
}
