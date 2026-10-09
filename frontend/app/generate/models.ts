export type GenerationModel = {
  label: string;
  modelId: string;
  recommended: boolean;
  description: string;
  provider: string;
};

export const DEFAULT_MODEL_ID = "anthropic/claude-haiku-5.5";
export const CUSTOM_MODEL_VALUE = "__custom__";

export const GENERATION_MODELS: readonly GenerationModel[] = [
  {
    label: "Claude Haiku 5.5",
    modelId: DEFAULT_MODEL_ID,
    recommended: true,
    description: "Fast preferred default for question generation.",
    provider: "Anthropic",
  },
  {
    label: "GPT-5.4 Mini",
    modelId: "openai/gpt-5.4-mini",
    recommended: false,
    description: "Compact OpenAI model with structured-output support.",
    provider: "OpenAI",
  },
  {
    label: "GPT-5 Mini",
    modelId: "openai/gpt-5-mini",
    recommended: false,
    description: "OpenAI mini model for general generation tasks.",
    provider: "OpenAI",
  },
  {
    label: "Qwen 3.5 Plus",
    modelId: "qwen/qwen3.5-plus-20260420",
    recommended: false,
    description: "Qwen model option for question generation.",
    provider: "Qwen",
  },
  {
    label: "Gemini 3.8 Flash",
    modelId: "google/gemini-3.8-flash",
    recommended: false,
    description: "Google Flash model option for question generation.",
    provider: "Google",
  },
] as const;

export function modelById(modelId: string): GenerationModel | undefined {
  return GENERATION_MODELS.find((model) => model.modelId === modelId);
}

export function selectionForModelId(modelId: string): string {
  return modelById(modelId) ? modelId : CUSTOM_MODEL_VALUE;
}

export function selectedModelId(selection: string, customModelId: string): string {
  return selection === CUSTOM_MODEL_VALUE ? customModelId.trim() : selection;
}

export function appendSelectedModel(
  formData: FormData,
  selection: string,
  customModelId: string,
): void {
  const modelId = selectedModelId(selection, customModelId);
  if (modelId) formData.append("model", modelId);
}
