import { Markdown } from "../../components/Markdown";
import { GeneratedSection } from "./generationFiles";

export function GeneratedSectionPreview({
  section,
  initiallyOpen = false,
  onDownload,
}: {
  section: GeneratedSection;
  initiallyOpen?: boolean;
  onDownload: (section: GeneratedSection) => void;
}) {
  return (
    <article className="generated-section">
      <header>
        <div>
          <h3>{section.section}</h3>
          <p>{section.questions.length} {section.questions.length === 1 ? "question" : "questions"}</p>
        </div>
        <button className="text-button" onClick={() => onDownload(section)} type="button">Download JSON</button>
      </header>
      <details className="generated-section-body" open={initiallyOpen}>
        <summary>Preview questions</summary>
        <ol className="generated-question-list">
          {section.questions.map((question) => (
            <li key={question.external_id}>
              <div className="question-list-meta">
                <span>{question.type}</span>
                <span>Difficulty {question.difficulty_level}</span>
                {question.source_page !== null && <span>Page {question.source_page}</span>}
              </div>
              <Markdown>{question.question}</Markdown>
              {question.tags.length > 0 && (
                <div className="generated-tags" aria-label="Tags">
                  {question.tags.map((tag) => <span key={tag}>{tag}</span>)}
                </div>
              )}
              <details>
                <summary>Show answer</summary>
                <div className="generated-answer"><Markdown>{question.answer}</Markdown></div>
              </details>
            </li>
          ))}
        </ol>
      </details>
    </article>
  );
}
