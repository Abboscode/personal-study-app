import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { StudyNote } from "@/app/notes/types";

import { NotesBrowser } from "./NotesBrowser";

const note: StudyNote = {
  id: 1,
  subject_id: 4,
  section_id: 8,
  section_name: "ADC Quantization",
  source_document_id: 2,
  source_document: { id: 2, filename: "adc.pdf" },
  source_page: "14",
  note_type: "formula",
  title: "Quantization Voltage",
  content_markdown: "### Formula\n\n\\[\nV_q=V_{FR}/2^{N_b}\n\\]",
  created_at: "2026-10-08T10:00:00Z",
  updated_at: "2026-10-08T10:00:00Z",
};

describe("NotesBrowser", () => {
  it("groups notes and uses the shared Markdown, math, and source renderer", () => {
    const html = renderToStaticMarkup(<NotesBrowser initialNotes={[note]} />);
    expect(html).toContain("ADC Quantization");
    expect(html).toContain("Quantization Voltage");
    expect(html).toContain("formula");
    expect(html).toContain("Page 14");
    expect(html).toContain("katex-display");
    expect(html).toContain("Open source");
    expect(html).toContain("Edit");
    expect(html).toContain("Delete");
  });
});
