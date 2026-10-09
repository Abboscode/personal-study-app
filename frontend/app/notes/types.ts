export type NoteType = "formula" | "theorem" | "concept" | "procedure";

export type NoteSourceDocument = {
  id: number;
  filename: string;
};

export type StudyNote = {
  id: number;
  subject_id: number;
  section_id: number;
  section_name: string;
  source_document_id: number | null;
  source_document: NoteSourceDocument | null;
  source_page: string | null;
  note_type: NoteType;
  title: string;
  content_markdown: string;
  created_at: string;
  updated_at: string;
};

export type GeneratedNote = {
  type: NoteType;
  title: string;
  content_markdown: string;
  source_page: string | number | null;
  duplicate: boolean;
};

export type GeneratedNoteSection = {
  subject: string;
  section: string;
  notes: GeneratedNote[];
};
