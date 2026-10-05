import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SectionCards } from "./SectionCards";

describe("SectionCards", () => {
  it("represents subject sections and links each one to its section page", () => {
    const html = renderToStaticMarkup(
      <SectionCards
        sections={[
          {
            id: 42,
            name: "Memory Fundamentals, Organization & Interface",
            description: null,
            question_count: 12,
            due_count: 4,
          },
          {
            id: 43,
            name: "SRAM",
            description: null,
            question_count: 20,
            due_count: 7,
          },
        ]}
      />,
    );

    expect(html).toContain("Memory Fundamentals, Organization &amp; Interface");
    expect(html).toContain("SRAM");
    expect(html).toContain('href="/sections/42"');
    expect(html).toContain('href="/sections/43"');
    expect(html).toContain("12");
    expect(html).toContain("4");
    expect(html).toContain("Practice");
  });
});

