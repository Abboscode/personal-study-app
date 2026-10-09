export type GeneratedQuestion = {
  external_id: string;
  type: "recall" | "concept" | "problem" | "code";
  question: string;
  answer: string;
  difficulty_level: number;
  tags: string[];
  source_page: string | number | null;
};

export type GeneratedSection = {
  schema_version: "1.0";
  subject: string;
  section: string;
  source: string | null;
  questions: GeneratedQuestion[];
};

export function sectionFilename(section: GeneratedSection): string {
  const slug = section.section
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "") || "generated-section";
  return `${slug}.json`;
}

export function serializeSection(section: GeneratedSection): string {
  return `${JSON.stringify(section, null, 2)}\n`;
}

export function generatedImportDocuments(sections: GeneratedSection[]) {
  return sections.map((section) => ({
    filename: sectionFilename(section),
    contents: serializeSection(section),
  }));
}
