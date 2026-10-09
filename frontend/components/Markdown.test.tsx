import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Markdown } from "./Markdown";

describe("Markdown", () => {
  it("renders imported inline and block LaTeX with KaTeX", () => {
    const html = renderToStaticMarkup(
      <Markdown>{String.raw`Inline math: \(256=2^8\).

\[
SIZE=N_{words}\times n_{bits}
\]`}</Markdown>,
    );

    expect(html.match(/class="katex"/g)).toHaveLength(2);
    expect(html).toContain("katex-display");
    expect(html).toContain("256");
    expect(html).toContain("N_{words}");
    expect(html).not.toContain(String.raw`\(256=2^8\)`);
  });

  it("preserves Markdown and highlighted fenced code without enabling raw HTML", () => {
    const markdown = [
      "**Important**",
      "",
      "`inline \\(not math\\)`",
      "",
      "```cpp",
      'auto formula = "\\[not math\\]";',
      "```",
      "",
      '<script>alert("unsafe")</script>',
    ].join("\n");
    const html = renderToStaticMarkup(
      <Markdown>{markdown}</Markdown>,
    );

    expect(html).toContain("<strong>Important</strong>");
    expect(html).toContain("hljs");
    expect(html).toContain(String.raw`\(not math\)`);
    expect(html).toContain(String.raw`\[not math\]`);
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
  });

  it("renders double-escaped model line breaks as Markdown paragraphs", () => {
    const markdown = String.raw`Each b_transport call adds 10 ns to delay, and the initiator then calls wait(delay).\n\n**Timing:** delay is declared inside the loop, so it is reset for each transaction.`;
    const html = renderToStaticMarkup(<Markdown>{markdown}</Markdown>);

    expect(html).toContain(
      "<p>Each b_transport call adds 10 ns to delay, and the initiator then calls wait(delay).</p>",
    );
    expect(html).toContain("<p><strong>Timing:</strong>");
    expect(html).not.toContain(String.raw`\n`);
  });

  it("does not reinterpret a lone programming escape as a line break", () => {
    const html = renderToStaticMarkup(
      <Markdown>{String.raw`Use the C++ escape \n for a newline.`}</Markdown>,
    );

    expect(html).toContain(String.raw`\n`);
  });
});
