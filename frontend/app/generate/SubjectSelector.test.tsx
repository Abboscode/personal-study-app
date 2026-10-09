import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SubjectSelector } from "./SubjectSelector";

describe("SubjectSelector", () => {
  it("renders every subject supplied by the backend, including unknown subjects", () => {
    const subjects = [
      { id: 1, name: "Computer Architecture" },
      { id: 2, name: "Electronics for Embedded Systems" },
      { id: 3, name: "Modeling and Optimization of Embedded Systems" },
      { id: 4, name: "Testing and Certification" },
      { id: 5, name: "A New Future Subject" },
    ];
    const html = renderToStaticMarkup(
      <SubjectSelector onChange={() => undefined} subjects={subjects} value="4" />,
    );

    expect((html.match(/<option/g) ?? [])).toHaveLength(subjects.length);
    for (const subject of subjects) expect(html).toContain(subject.name);
    expect(html).toContain('<option value="4" selected="">Testing and Certification</option>');
  });
});
