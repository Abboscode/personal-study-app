"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { ModelSelector } from "@/app/generate/ModelSelector";
import {
  appendSelectedModel,
  CUSTOM_MODEL_VALUE,
  DEFAULT_MODEL_ID,
  modelById,
  selectedModelId,
  selectionForModelId,
} from "@/app/generate/models";
import { GenerationSubject, SubjectSelector } from "@/app/generate/SubjectSelector";
import { responseError } from "@/app/generate/generationUi";
import type { GeneratedNoteSection } from "@/app/notes/types";
import { Markdown } from "@/components/Markdown";
import { SourceReference } from "@/components/SourceReference";

type Config = { default_model: string; api_key_configured: boolean };
type LectureSource = { id: number; original_filename: string; page_count: number | null };
type Estimate = { pages: number; extracted_characters: number; estimated_input_tokens: number };
type Preview = Estimate & {
  model: string;
  profile: string;
  source: string;
  source_document_id: number;
  validation_status: "valid";
  sections: GeneratedNoteSection[];
};
type SaveSummary = { received: number; saved: number; duplicates: number; section_ids: number[] };

export default function GenerateNotesPage() {
  const [subjects, setSubjects] = useState<GenerationSubject[]>([]);
  const [subjectId, setSubjectId] = useState("");
  const [sources, setSources] = useState<LectureSource[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [sourceMode, setSourceMode] = useState<"existing" | "upload">("existing");
  const [file, setFile] = useState<File | null>(null);
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [modelSelection, setModelSelection] = useState(DEFAULT_MODEL_ID);
  const [customModelId, setCustomModelId] = useState("");
  const [autoDetect, setAutoDetect] = useState(true);
  const [sectionName, setSectionName] = useState("");
  const [config, setConfig] = useState<Config | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [saveSummary, setSaveSummary] = useState<SaveSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [estimating, setEstimating] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const model = selectedModelId(modelSelection, customModelId);

  const loadInitial = useCallback(async () => {
    setLoading(true);
    try {
      const [subjectsResponse, configResponse] = await Promise.all([
        fetch("/api/subjects", { cache: "no-store" }),
        fetch("/api/generate/config", { cache: "no-store" }),
      ]);
      if (!subjectsResponse.ok || !configResponse.ok) throw new Error("Could not load note generation settings");
      const loadedSubjects: GenerationSubject[] = await subjectsResponse.json();
      const loadedConfig: Config = await configResponse.json();
      const params = new URLSearchParams(window.location.search);
      const requestedSubject = params.get("subject_id") ?? "";
      const initialSubject = loadedSubjects.some((item) => String(item.id) === requestedSubject)
        ? requestedSubject
        : loadedSubjects[0] ? String(loadedSubjects[0].id) : "";
      const requestedSection = params.get("section_name");
      setSubjects(loadedSubjects);
      setSubjectId(initialSubject);
      setConfig(loadedConfig);
      const selection = selectionForModelId(loadedConfig.default_model);
      setModelSelection(selection);
      setCustomModelId(selection === CUSTOM_MODEL_VALUE ? loadedConfig.default_model : "");
      if (requestedSection) { setAutoDetect(false); setSectionName(requestedSection); }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load note generation settings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadInitial(); }, [loadInitial]);

  useEffect(() => {
    if (!subjectId) return;
    const controller = new AbortController();
    fetch(`/api/subjects/${subjectId}/lecture-sources`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("Could not load lecture materials");
        return response.json() as Promise<LectureSource[]>;
      })
      .then((loadedSources) => {
        setSources(loadedSources);
        const requestedSource = new URLSearchParams(window.location.search).get("source_id") ?? "";
        const nextSource = loadedSources.some((item) => String(item.id) === requestedSource)
          ? requestedSource
          : loadedSources[0] ? String(loadedSources[0].id) : "";
        setSourceId(nextSource);
        if (requestedSource && nextSource === requestedSource) setSourceMode("existing");
        else if (loadedSources.length === 0) setSourceMode("upload");
      })
      .catch((reason) => {
        if (reason instanceof Error && reason.name !== "AbortError") setError(reason.message);
      });
    return () => controller.abort();
  }, [subjectId]);

  async function selectPdf(selected: File | null) {
    setFile(selected);
    setEstimate(null);
    setPreview(null);
    setSaveSummary(null);
    if (!selected) return;
    setEstimating(true);
    const body = new FormData();
    body.append("file", selected);
    try {
      const response = await fetch("/api/generate/estimate", { method: "POST", body });
      if (!response.ok) throw await responseError(response, "Could not analyze the PDF");
      setEstimate(await response.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not analyze the PDF");
    } finally {
      setEstimating(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setGenerating(true);
    setError("");
    setPreview(null);
    setSaveSummary(null);
    const body = new FormData();
    body.append("subject_id", subjectId);
    body.append("section_mode", autoDetect ? "auto" : "manual");
    if (!autoDetect) body.append("section_name", sectionName.trim());
    if (sourceMode === "existing") body.append("source_document_id", sourceId);
    else if (file) body.append("file", file);
    appendSelectedModel(body, modelSelection, customModelId);
    try {
      const response = await fetch("/api/notes/generation", { method: "POST", body });
      if (!response.ok) throw await responseError(response, "Note generation failed");
      setPreview(await response.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Note generation failed");
    } finally {
      setGenerating(false);
    }
  }

  async function saveNotes() {
    if (!preview) return;
    setSaving(true);
    setError("");
    try {
      const response = await fetch("/api/notes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          subject_id: Number(subjectId),
          source_document_id: preview.source_document_id,
          sections: preview.sections,
        }),
      });
      if (!response.ok) throw await responseError(response, "Could not save notes");
      setSaveSummary(await response.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save notes");
    } finally {
      setSaving(false);
    }
  }

  const sourceReady = sourceMode === "existing" ? Boolean(sourceId) : Boolean(file && estimate);
  const canGenerate = Boolean(subjectId && sourceReady && model && (autoDetect || sectionName.trim()));
  const previewModel = preview ? modelById(preview.model) : undefined;

  return (
    <div className="page-shell generate-page">
      <section className="generate-intro"><p className="eyebrow">CONCISE REFERENCE MATERIAL</p><h1>Generate notes</h1><p className="lede">Create compact formulas, theorems, concepts, and procedures. Notes stay separate from review scheduling.</p></section>
      {error && <p className="error" role="alert">{error}</p>}
      {config && !config.api_key_configured && <p className="configuration-note">OpenRouter is not configured.</p>}
      {loading ? <p className="muted">Loading generation settings…</p> : subjects.length === 0 ? <section className="empty-state"><h2>Create a subject first</h2></section> : (
        <form className="generation-form" onSubmit={submit}>
          <SubjectSelector subjects={subjects} value={subjectId} onChange={(value) => { setSubjectId(value); setPreview(null); }} />
          <fieldset className="field-group section-choice"><legend>Source</legend><label><input checked={sourceMode === "existing"} disabled={sources.length === 0} name="source-mode" onChange={() => setSourceMode("existing")} type="radio" /> Existing lecture</label><label><input checked={sourceMode === "upload"} name="source-mode" onChange={() => setSourceMode("upload")} type="radio" /> Upload new PDF</label></fieldset>
          {sourceMode === "existing" ? <label className="field-group"><span>Lecture</span><select value={sourceId} onChange={(event) => setSourceId(event.target.value)}>{sources.map((source) => <option key={source.id} value={source.id}>{source.original_filename}{source.page_count ? ` · ${source.page_count} pages` : ""}</option>)}</select></label> : <label className="field-group"><span>PDF</span><input accept="application/pdf,.pdf" type="file" onChange={(event) => void selectPdf(event.target.files?.[0] ?? null)} />{estimating && <small>Analyzing PDF…</small>}{estimate && <small>{estimate.pages} pages · about {estimate.estimated_input_tokens.toLocaleString()} input tokens</small>}</label>}
          <fieldset className="field-group section-choice"><legend>Section</legend><label><input checked={autoDetect} name="section-mode" onChange={() => setAutoDetect(true)} type="radio" /> Detect automatically</label><label><input checked={!autoDetect} name="section-mode" onChange={() => setAutoDetect(false)} type="radio" /> Specify section</label>{!autoDetect && <input aria-label="Section name" placeholder="e.g. ADC Quantization" value={sectionName} onChange={(event) => setSectionName(event.target.value)} />}</fieldset>
          <ModelSelector customModelId={customModelId} onCustomModelChange={setCustomModelId} onSelectionChange={setModelSelection} selection={modelSelection} />
          <button className="primary-button" disabled={!canGenerate || generating} type="submit">{generating ? "Generating notes…" : "Generate notes"}</button>
        </form>
      )}

      {preview && <section className="generation-preview">
        <header className="preview-heading"><div><p className="eyebrow">GENERATED NOTES</p><h2>{preview.sections.reduce((total, section) => total + section.notes.length, 0)} validated notes</h2><p>{previewModel?.label ?? preview.model} · {preview.model}</p></div><span className="valid-badge">Schema valid</span></header>
        <div className="generated-note-sections">{preview.sections.map((section) => <section key={section.section}><h3>{section.section}</h3><div className="note-card-grid">{section.notes.map((note) => <article className="generated-note-card" key={`${note.type}-${note.title}`}><header><div><span className="note-type-badge">{note.type}</span><h4>{note.title}</h4></div>{note.duplicate && <span className="duplicate-badge">Already saved</span>}</header><Markdown>{note.content_markdown}</Markdown><SourceReference sourceDocument={{ id: preview.source_document_id, filename: preview.source }} sourcePage={note.source_page} /></article>)}</div></section>)}</div>
        <div className="preview-actions"><button className="primary-button" disabled={saving || Boolean(saveSummary)} onClick={() => void saveNotes()} type="button">{saving ? "Saving…" : saveSummary ? "Saved" : "Save notes"}</button><button className="secondary-button" disabled={saving} onClick={() => { setPreview(null); setSaveSummary(null); }} type="button">Discard</button></div>
        {saveSummary && <div className="approval-result"><strong>Notes saved.</strong> {saveSummary.saved} new, {saveSummary.duplicates} duplicates skipped.<Link href={`/subjects/${subjectId}/notes`}>Browse notes</Link></div>}
      </section>}
    </div>
  );
}
