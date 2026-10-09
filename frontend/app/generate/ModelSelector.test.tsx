import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ModelSelector } from "./ModelSelector";
import {
  appendSelectedModel,
  CUSTOM_MODEL_VALUE,
  DEFAULT_MODEL_ID,
  GENERATION_MODELS,
  selectedModelId,
} from "./models";

const callbacks = {
  onSelectionChange: () => undefined,
  onCustomModelChange: () => undefined,
};

describe("ModelSelector", () => {
  it("renders every centralized model and marks Haiku as the default", () => {
    const html = renderToStaticMarkup(
      <ModelSelector
        {...callbacks}
        customModelId=""
        selection={DEFAULT_MODEL_ID}
      />,
    );

    for (const model of GENERATION_MODELS) {
      expect(html).toContain(model.label);
      expect(html).toContain(model.modelId);
    }
    expect(html).toContain("Claude Haiku 5.5 (recommended)");
    expect(html).toContain(`value="${DEFAULT_MODEL_ID}" selected=""`);
    expect(html).toContain("Custom model…");
  });

  it("only renders the custom model input for the custom selection", () => {
    const presetHtml = renderToStaticMarkup(
      <ModelSelector
        {...callbacks}
        customModelId=""
        selection={DEFAULT_MODEL_ID}
      />,
    );
    const customHtml = renderToStaticMarkup(
      <ModelSelector
        {...callbacks}
        customModelId="vendor/my-model"
        selection={CUSTOM_MODEL_VALUE}
      />,
    );

    expect(presetHtml).not.toContain("OpenRouter model ID");
    expect(customHtml).toContain("OpenRouter model ID");
    expect(customHtml).toContain('value="vendor/my-model"');
  });

  it("sends the selected preset or trimmed custom model ID", () => {
    const preset = new FormData();
    appendSelectedModel(preset, "openai/gpt-5-mini", "");
    expect(preset.get("model")).toBe("openai/gpt-5-mini");

    const custom = new FormData();
    appendSelectedModel(custom, CUSTOM_MODEL_VALUE, "  vendor/custom-model  ");
    expect(custom.get("model")).toBe("vendor/custom-model");
    expect(selectedModelId(CUSTOM_MODEL_VALUE, "  vendor/custom-model  ")).toBe(
      "vendor/custom-model",
    );
  });
});
