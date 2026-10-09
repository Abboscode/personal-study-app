export const GENERATION_LOADING_STATUS =
  "Extracting lecture, generating questions, and validating result…";

const STAGE_LABELS: Record<string, string> = {
  pdf_storage: "PDF storage",
  pdf_extraction: "PDF extraction",
  prompt_composition: "prompt composition",
  openrouter_request: "OpenRouter request",
  response_parsing: "response parsing",
  schema_validation: "schema validation",
  preview_creation: "preview creation",
};

export async function responseError(
  response: Response,
  fallback: string,
): Promise<Error> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object") {
      const record = body as Record<string, unknown>;
      if (typeof record.message === "string") {
        if (typeof record.stage === "string") {
          const stage =
            STAGE_LABELS[record.stage] ?? record.stage.replaceAll("_", " ");
          return new Error(`Generation failed during ${stage}.\n${record.message}`);
        }
        return new Error(record.message);
      }
      if (typeof record.detail === "string") return new Error(record.detail);
      if (record.detail) return new Error(JSON.stringify(record.detail));
    }
  } catch {
    // Fall through to the safe caller-provided message.
  }
  return new Error(fallback);
}

type GenerationFormState = {
  subjectId: string;
  pdfSelected: boolean;
  estimateReady: boolean;
  model: string;
  sectionMode: "auto" | "manual";
  sectionName: string;
};

export function generationFormError(state: GenerationFormState): string | null {
  if (!state.subjectId) return "Select a subject";
  if (!state.pdfSelected) return "Select a lecture PDF";
  if (!state.estimateReady) return "Wait for PDF analysis to finish";
  if (!state.model.trim()) return "Enter an OpenRouter model";
  if (state.sectionMode === "manual" && !state.sectionName.trim()) {
    return "Enter a manual section name";
  }
  return null;
}
