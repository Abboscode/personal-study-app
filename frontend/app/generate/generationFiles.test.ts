import { describe, expect, it } from "vitest";

import {
  GeneratedSection,
  generatedImportDocuments,
  sectionFilename,
  serializeSection,
} from "./generationFiles";

const section: GeneratedSection = {
  schema_version: "1.0",
  subject: "Electronics for Embedded Systems",
  section: "SRAM & Timing",
  source: "lecture.pdf",
  questions: [
    {
      external_id: "efes-sram-read",
      type: "concept",
      question: "Why is sensing needed?",
      answer: "Because \\(\\Delta V\\) is small.",
      difficulty_level: 2,
      tags: ["sram"],
      source_page: 4,
    },
  ],
};

describe("generated section files", () => {
  it("creates a safe JSON filename", () => {
    expect(sectionFilename(section)).toBe("sram-timing.json");
  });

  it("serializes the unchanged import schema and escaped LaTeX", () => {
    const parsed = JSON.parse(serializeSection(section));
    expect(parsed).toEqual(section);
    expect(parsed.questions[0].answer).toBe("Because \\(\\Delta V\\) is small.");
  });

  it("prepares approved sections for the existing batch importer", () => {
    const second = { ...section, section: "DRAM" };
    const documents = generatedImportDocuments([section, second]);

    expect(documents.map((document) => document.filename)).toEqual([
      "sram-timing.json",
      "dram.json",
    ]);
    expect(documents.map((document) => JSON.parse(document.contents))).toEqual([
      section,
      second,
    ]);
  });
});
