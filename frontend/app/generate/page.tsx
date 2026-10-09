"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { GeneratedSectionPreview } from "./GeneratedSectionPreview";
import {
  generatedImportDocuments,
  GeneratedSection,
  sectionFilename,
  serializeSection,
} from "./generationFiles";
import {
  GENERATION_LOADING_STATUS,
  generationFormError,
  responseError,
} from "./generationUi";
import { ModelSelector } from "./ModelSelector";
import {
  appendSelectedModel,
  CUSTOM_MODEL_VALUE,
  DEFAULT_MODEL_ID,
  modelById,
  selectedModelId,
  selectionForModelId,
} from "./models";
import { GenerationSubject, SubjectSelector } from "./SubjectSelector";

type Config = {
  provider: "openrouter";
  default_model: string;
  api_key_configured: boolean;
};
type Estimate = {
  filename: string;
  pages: number;
  extracted_characters: number;
  estimated_input_tokens: number;
};
type Preview = Omit<Estimate, "filename"> & {
  provider: "openrouter";
  model: string;
  profile: string;
  validation_status: "valid";
  source: string;
  source_document_id: number;
  sections: GeneratedSection[];
};
type ImportSummary = {
  files_processed: number;
  questions_received: number;
  questions_imported: number;
  duplicates: number;
  errors: number;
};

export default function GenerateQuestionsPage() {
  const [subjects, setSubjects] = useState<GenerationSubject[]>([]);
  const [subjectId, setSubjectId] = useState("");
  const [subjectsLoading, setSubjectsLoading] = useState(true);
  const [subjectsError, setSubjectsError] = useState("");
  const [config, setConfig] = useState<Config | null>(null);
  const [modelSelection, setModelSelection] = useState(DEFAULT_MODEL_ID);
  const [customModelId, setCustomModelId] = useState("");
  const [pdf, setPdf] = useState<File | null>(null);
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [estimateLoading, setEstimateLoading] = useState(false);
  const [autoDetect, setAutoDetect] = useState(true);
  const [sectionName, setSectionName] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [importSummary, setImportSummary] = useState<ImportSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState("");
  const model = selectedModelId(modelSelection, customModelId);

  const loadSubjects = useCallback(async () => {
    setSubjectsLoading(true);
    setSubjectsError("");
    try {
      const response = await fetch("/api/subjects", { cache: "no-store" });
      if (!response.ok) throw new Error("Could not load subjects");
      const loadedSubjects: GenerationSubject[] = await response.json();
      setSubjects(loadedSubjects);
      setSubjectId((current) => {
        if (loadedSubjects.some((subject) => String(subject.id) === current)) return current;
        return loadedSubjects.length > 0 ? String(loadedSubjects[0].id) : "";
      });
    } catch (reason) {
      setSubjectsError(reason instanceof Error ? reason.message : "Could not load subjects");
    } finally {
      setSubjectsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSubjects();
    fetch("/api/generate/config")
      .then(async (response) => {
        if (!response.ok) throw new Error("Could not load generation settings");
        return response.json() as Promise<Config>;
      })
      .then((loadedConfig) => {
        setConfig(loadedConfig);
        const selection = selectionForModelId(loadedConfig.default_model);
        setModelSelection(selection);
        setCustomModelId(
          selection === CUSTOM_MODEL_VALUE ? loadedConfig.default_model : "",
        );
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Could not load generation settings"));
  }, [loadSubjects]);

  async function selectPdf(file: File | null) {
    setPdf(file);
    setEstimate(null);
    setPreview(null);
    setImportSummary(null);
    setError("");
    if (!file) return;
    setEstimateLoading(true);
    const body = new FormData();
    body.append("file", file);
    try {
      const response = await fetch("/api/generate/estimate", { method: "POST", body });
      if (!response.ok) throw await responseError(response, "Could not analyze the PDF");
      setEstimate(await response.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not analyze the PDF");
    } finally {
      setEstimateLoading(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!pdf || !subjectId || !estimate) return;
    setLoading(true);
    setError("");
    setPreview(null);
    setImportSummary(null);
    const body = new FormData();
    body.append("subject_id", subjectId);
    body.append("file", pdf);
    body.append("section_mode", autoDetect ? "auto" : "manual");
    if (!autoDetect) body.append("section_name", sectionName);
    appendSelectedModel(body, modelSelection, customModelId);
    try {
      const response = await fetch("/api/generation", { method: "POST", body });
      if (!response.ok) throw await responseError(response, "Question generation failed");
      setPreview(await response.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Question generation failed");
    } finally {
      setLoading(false);
    }
  }

  async function importAll() {
    if (!preview) return;
    setImporting(true);
    setError("");
    const body = new FormData();
    body.append("source_document_id", String(preview.source_document_id));
    generatedImportDocuments(preview.sections).forEach((document) => {
      body.append(
        "files",
        new File([document.contents], document.filename, { type: "application/json" }),
      );
    });
    try {
      const response = await fetch("/api/import/batch", { method: "POST", body });
      if (!response.ok) throw await responseError(response, "Import failed");
      setImportSummary(await response.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Import failed");
    } finally {
      setImporting(false);
    }
  }

  function downloadSection(section: GeneratedSection) {
    const url = URL.createObjectURL(
      new Blob([serializeSection(section)], { type: "application/json" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = sectionFilename(section);
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function discard() {
    setPreview(null);
    setImportSummary(null);
    setError("");
  }

  const currentFormError = generationFormError({
    subjectId,
    pdfSelected: Boolean(pdf),
    estimateReady: Boolean(estimate),
    model,
    sectionMode: autoDetect ? "auto" : "manual",
    sectionName,
  });
  const canGenerate = currentFormError === null;

  return (
    <div className="page-shell generate-page">
      <section className="generate-intro">
        <p className="eyebrow">AI-ASSISTED INGESTION</p>
        <h1>Generate questions</h1>
        <p className="lede">Turn a text-based lecture PDF into validated question JSON. Nothing is saved until you approve the preview.</p>
      </section>

      {error && <p className="error" role="alert">{error}</p>}
      {config && !config.api_key_configured && (
        <p className="configuration-note" role="status">OpenRouter is not configured yet. Add <code>OPENROUTER_API_KEY</code> to the backend environment before generating.</p>
      )}
      {subjectsLoading && (
        <section className="subject-loading-state" role="status">
          <span className="loading-spinner" aria-hidden="true" />
          <div><strong>Loading subjects</strong><span>Reading your library from the backend…</span></div>
        </section>
      )}
      {!subjectsLoading && subjectsError && (
        <section className="subject-load-error" role="alert">
          <div><strong>Subjects could not be loaded.</strong><span>{subjectsError}</span></div>
          <button className="secondary-button" onClick={() => void loadSubjects()} type="button">Try again</button>
        </section>
      )}
      {!subjectsLoading && !subjectsError && subjects.length === 0 && (
        <section className="empty-state">
          <h2>Create a subject first</h2>
          <p>No subjects were returned by the backend. Import questions or create a subject first.</p>
          <Link className="secondary-button" href="/import">Import questions</Link>
        </section>
      )}

      {!subjectsLoading && !subjectsError && subjects.length > 0 && (
        <form className="generation-form" onSubmit={submit}>
          <SubjectSelector onChange={setSubjectId} subjects={subjects} value={subjectId} />

          <label className="field-group">
            <span>Lecture PDF</span>
            <input
              accept="application/pdf,.pdf"
              type="file"
              onChange={(event) => void selectPdf(event.target.files?.[0] ?? null)}
            />
          </label>

          <fieldset className="field-group section-choice">
            <legend>Section</legend>
            <label><input checked={autoDetect} name="section-mode" onChange={() => setAutoDetect(true)} type="radio" /> Detect automatically</label>
            <label><input checked={!autoDetect} name="section-mode" onChange={() => setAutoDetect(false)} type="radio" /> Specify section</label>
            {!autoDetect && (
              <input
                aria-label="Section name"
                onChange={(event) => setSectionName(event.target.value)}
                placeholder="e.g. SRAM"
                value={sectionName}
              />
            )}
          </fieldset>

          <ModelSelector
            customModelId={customModelId}
            onCustomModelChange={setCustomModelId}
            onSelectionChange={setModelSelection}
            selection={modelSelection}
          />

          <div className="input-estimate" aria-live="polite">
            {estimateLoading && <span>Analyzing PDF text…</span>}
            {!estimateLoading && estimate && (
              <>
                <strong>Approximate provider input</strong>
                <span>{estimate.pages} pages · {estimate.extracted_characters.toLocaleString()} characters · about {estimate.estimated_input_tokens.toLocaleString()} tokens</span>
                <small>Token count uses a simple four-characters-per-token estimate; actual billing varies by model.</small>
              </>
            )}
            {!estimateLoading && !estimate && <span>Select a text-based PDF to estimate its input size before generation.</span>}
          </div>

          <button className="primary-button" disabled={!canGenerate || loading} type="submit">
            {loading ? "Working…" : "Generate questions"}
          </button>
          {loading && (
            <div className="generation-loading" role="status">
              <span className="loading-spinner" aria-hidden="true" />
              <div><strong>Generating your preview</strong><span>{GENERATION_LOADING_STATUS}</span></div>
            </div>
          )}
        </form>
      )}

      {preview && (
        <section className="generation-preview" aria-live="polite">
          <header className="preview-heading">
            <div>
              <p className="eyebrow">GENERATED SECTIONS</p>
              <h2>{preview.sections.length} validated {preview.sections.length === 1 ? "section" : "sections"}</h2>
              <div className="preview-model">
                <span>Model</span>
                <strong>{modelById(preview.model)?.label ?? "Custom model"}</strong>
                {modelById(preview.model)?.recommended && (
                  <span className="recommended-badge">Recommended</span>
                )}
                <code>{preview.model}</code>
              </div>
              <p>Profile: {preview.profile.replaceAll("_", " ")}</p>
              <p className="preview-source"><strong>Source:</strong> {preview.source}</p>
            </div>
            <span className="valid-badge">Schema valid</span>
          </header>

          <div className="generated-sections">
            {preview.sections.map((section) => (
              <GeneratedSectionPreview
                initiallyOpen={preview.sections.length === 1}
                key={section.section}
                onDownload={downloadSection}
                section={section}
              />
            ))}
          </div>

          <div className="preview-actions">
            <button className="primary-button" disabled={importing || Boolean(importSummary)} onClick={() => void importAll()} type="button">
              {importing ? "Importing…" : importSummary ? "Imported" : preview.sections.length === 1 ? "Import questions" : "Import all"}
            </button>
            <button className="secondary-button" disabled={importing} onClick={discard} type="button">Discard</button>
          </div>

          {importSummary && (
            <div className="approval-result" role="status">
              <strong>Import complete.</strong> {importSummary.questions_imported} imported, {importSummary.duplicates} duplicates, {importSummary.errors} errors across {importSummary.files_processed} files.
              <Link href={`/subjects/${subjectId}`}>Open subject</Link>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
