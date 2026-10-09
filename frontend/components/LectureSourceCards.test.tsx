import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { LectureSourceCards } from "./LectureSourceCards";

describe("LectureSourceCards", () => {
  it("renders lecture filenames and linked counts", () => {
    const html = renderToStaticMarkup(
      <LectureSourceCards
        sources={[{
          id: 8,
          subject_id: 2,
          original_filename: "memories.pdf",
          page_count: 42,
          uploaded_at: "2026-10-07T10:00:00Z",
          question_count: 63,
          note_count: 5,
          section_count: 4,
          file_url: "/api/lecture-sources/8/file",
        }]}
      />,
    );
    expect(html).toContain("memories.pdf");
    expect(html).toContain("42 pages");
    expect(html).toContain("63");
    expect(html).toContain("5");
    expect(html).toContain("/lecture-sources/8");
  });
});
