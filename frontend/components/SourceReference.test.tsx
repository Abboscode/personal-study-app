import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SourceReference, sourceFileHref } from "./SourceReference";

describe("SourceReference", () => {
  it("adds a PDF page fragment when a source page is available", () => {
    expect(sourceFileHref(12, "Page 4")).toBe(
      "/api/lecture-sources/12/file#page=4",
    );
    expect(sourceFileHref(12, null)).toBe("/api/lecture-sources/12/file");
  });

  it("renders linked documents and unlinked legacy source text", () => {
    const linked = renderToStaticMarkup(
      <SourceReference
        sourceDocument={{ id: 3, filename: "memories.pdf" }}
        sourcePage="7"
      />,
    );
    expect(linked).toContain("memories.pdf · Page 7");
    expect(linked).toContain("/api/lecture-sources/3/file#page=7");

    const legacy = renderToStaticMarkup(
      <SourceReference sourcePage="2" sourceText="legacy.pdf" />,
    );
    expect(legacy).toContain("legacy.pdf · Page 2");
    expect(legacy).not.toContain("Open source");
  });
});
