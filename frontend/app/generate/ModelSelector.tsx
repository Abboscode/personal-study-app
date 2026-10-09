import {
  CUSTOM_MODEL_VALUE,
  GENERATION_MODELS,
  modelById,
} from "./models";

export function ModelSelector({
  selection,
  customModelId,
  onSelectionChange,
  onCustomModelChange,
}: {
  selection: string;
  customModelId: string;
  onSelectionChange: (modelId: string) => void;
  onCustomModelChange: (modelId: string) => void;
}) {
  const selectedModel = modelById(selection);

  return (
    <fieldset className="field-group model-selector">
      <legend>Model</legend>
      <select
        aria-label="Model"
        value={selection}
        onChange={(event) => onSelectionChange(event.target.value)}
      >
        {GENERATION_MODELS.map((model) => (
          <option key={model.modelId} value={model.modelId}>
            {model.label}{model.recommended ? " (recommended)" : ""}
          </option>
        ))}
        <option value={CUSTOM_MODEL_VALUE}>Custom model…</option>
      </select>

      {selectedModel && (
        <small>
          {selectedModel.provider} · {selectedModel.description}
        </small>
      )}

      {selection === CUSTOM_MODEL_VALUE && (
        <label className="custom-model-field">
          <span>OpenRouter model ID</span>
          <input
            autoComplete="off"
            onChange={(event) => onCustomModelChange(event.target.value)}
            placeholder="provider/model-id"
            type="text"
            value={customModelId}
          />
        </label>
      )}
    </fieldset>
  );
}
