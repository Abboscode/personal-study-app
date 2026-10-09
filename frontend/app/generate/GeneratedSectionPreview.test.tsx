import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { GeneratedSectionPreview } from "./GeneratedSectionPreview";
import { GeneratedSection } from "./generationFiles";

const section: GeneratedSection = {
  schema_version: "1.0",
  subject: "Electronics for Embedded Systems",
  section: "SRAM",
  source: "lecture.pdf",
  questions: [
    {
      external_id: "efes-sram-sense-amplifier",
      type: "code",
      question: [
        String.raw`The delay is \(T=10\text{ ms}\).`,
        "",
        "**SystemC/C++ event thread:**",
        "",
        "```cpp",
        "SC_THREAD(RUN);",
        "wait(car.posedge_event());",
        "```",
      ].join("\n"),
      answer: [
        "The quantization interval is:",
        "",
        String.raw`\[`,
        String.raw`V_q=\frac{V_{FR}}{2^{N_b}}`,
        String.raw`\]`,
      ].join("\n"),
      difficulty_level: 2,
      tags: ["sram", "timing"],
      source_page: 7,
    },
  ],
};

describe("GeneratedSectionPreview", () => {
  it("uses the shared Markdown pipeline for math, code, and identifiers", () => {
    const parsedSection = JSON.parse(JSON.stringify(section)) as GeneratedSection;
    const html = renderToStaticMarkup(
      <GeneratedSectionPreview
        initiallyOpen
        onDownload={() => undefined}
        section={parsedSection}
      />,
    );
    const visibleText = html.replace(/<[^>]+>/g, "");

    expect(html).toContain("SRAM");
    expect(html).toContain("Preview questions");
    expect(html).toContain("<strong>SystemC/C++ event thread:</strong>");
    expect(html).toContain("Show answer");
    expect(html).toContain("Difficulty 2");
    expect(html).toContain("Page 7");
    expect(html).toContain("sram");
    expect(html).toContain("timing");
    expect(html.match(/class="katex"/g)).toHaveLength(2);
    expect(html).toContain("katex-display");
    expect(html).toContain("T=10\\text{ ms}");
    expect(html).toContain("V_q=\\frac{V_{FR}}{2^{N_b}}");
    expect(html).toContain("hljs");
    expect(html).toContain("SC_THREAD");
    expect(visibleText).toContain("car.posedge_event()");
    expect(html).not.toContain(String.raw`\(T=10\text{ ms}\)`);
    expect(html).not.toContain(String.raw`\[`);
    expect(html).not.toContain(String.raw`\]`);
  });

  it("renders double-escaped answer paragraphs through the shared renderer", () => {
    const escapedSection: GeneratedSection = {
      ...section,
      questions: [
        {
          ...section.questions[0],
          answer: String.raw`Each b_transport call adds 10 ns, and the initiator calls wait(delay).\n\n**Timing:** delay is reset to 0 ns for each transaction.`,
        },
      ],
    };
    const html = renderToStaticMarkup(
      <GeneratedSectionPreview
        initiallyOpen
        onDownload={() => undefined}
        section={escapedSection}
      />,
    );

    expect(html).toContain("wait(delay).</p>");
    expect(html).toContain("<p><strong>Timing:</strong>");
    expect(html).not.toContain(String.raw`\n\n`);
  });
});
