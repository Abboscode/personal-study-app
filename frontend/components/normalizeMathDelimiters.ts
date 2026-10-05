/**
 * Convert the LaTeX delimiters used by imported question JSON into the dollar
 * delimiters understood by remark-math. Markdown code is deliberately left
 * untouched so examples containing LaTeX source remain examples.
 */
export function normalizeMathDelimiters(markdown: string): string {
  let fence: { character: "`" | "~"; length: number } | null = null;
  let inlineCodeTicks = 0;

  return markdown
    .split(/(\r?\n)/)
    .map((line) => {
      if (line === "\n" || line === "\r\n") return line;

      if (fence) {
        const closingFence = new RegExp(
          `^ {0,3}${fence.character}{${fence.length},}[ \\t]*$`,
        );
        if (closingFence.test(line)) fence = null;
        return line;
      }

      if (inlineCodeTicks === 0) {
        const openingFence = line.match(/^ {0,3}(`{3,}|~{3,})/);
        if (openingFence) {
          const marker = openingFence[1];
          fence = {
            character: marker[0] as "`" | "~",
            length: marker.length,
          };
          return line;
        }
      }

      let normalized = "";
      let index = 0;

      while (index < line.length) {
        if (line[index] === "`") {
          let end = index + 1;
          while (line[end] === "`") end += 1;
          const tickCount = end - index;

          if (inlineCodeTicks === 0) inlineCodeTicks = tickCount;
          else if (inlineCodeTicks === tickCount) inlineCodeTicks = 0;

          normalized += line.slice(index, end);
          index = end;
          continue;
        }

        if (
          inlineCodeTicks === 0 &&
          line[index] === "\\" &&
          !isEscaped(line, index)
        ) {
          const delimiter = line[index + 1];
          if (delimiter === "(" || delimiter === ")") {
            normalized += "$";
            index += 2;
            continue;
          }
          if (delimiter === "[" || delimiter === "]") {
            normalized += "$$";
            index += 2;
            continue;
          }
        }

        normalized += line[index];
        index += 1;
      }

      return normalized;
    })
    .join("");
}

function isEscaped(value: string, index: number): boolean {
  let precedingBackslashes = 0;
  for (let cursor = index - 1; cursor >= 0 && value[cursor] === "\\"; cursor -= 1) {
    precedingBackslashes += 1;
  }
  return precedingBackslashes % 2 === 1;
}
