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
});
