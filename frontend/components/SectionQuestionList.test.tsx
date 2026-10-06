import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  SectionQuestionList,
  toggleExpandedQuestion,
  type SectionQuestion,
} from "./SectionQuestionList";

const questions: SectionQuestion[] = [
  {
    id: 7,
    external_id: "memory-007",
    question_type: "concept",
    question: String.raw`What is \(2^8\)?`,
    answer: String.raw`It is **256**.

\[
2^8=256
\]`,
    difficulty_level: 1,
    tags: ["memory"],
    is_due: true,
  },
  {
    id: 8,
    external_id: "memory-008",
    question_type: "recall",
    question: "What is SRAM?",
    answer: "Static random-access memory.",
    difficulty_level: 1,
    tags: [],
    is_due: false,
  },
];

describe("SectionQuestionList", () => {
  it("keeps every answer collapsed by default", () => {
    const html = renderToStaticMarkup(<SectionQuestionList questions={questions} />);

    expect(html.match(/Show answer/g)).toHaveLength(2);
    expect(html).not.toContain("It is <strong>256</strong>");
    expect(html).not.toContain("Static random-access memory");
  });

  it("renders an expanded answer with the shared Markdown and math pipeline", () => {
    const html = renderToStaticMarkup(
      <SectionQuestionList questions={questions} initiallyExpandedQuestionIds={[7]} />,
    );

    expect(html).toContain("Hide answer");
    expect(html).toContain("It is <strong>256</strong>");
    expect(html).toContain("katex-display");
    expect(html).toContain("Show answer");
  });

  it("toggles questions independently", () => {
    let expanded = toggleExpandedQuestion(new Set(), 7);
    expanded = toggleExpandedQuestion(expanded, 8);
    expect([...expanded]).toEqual([7, 8]);

    expanded = toggleExpandedQuestion(expanded, 7);
    expect([...expanded]).toEqual([8]);
  });
});
