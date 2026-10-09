import { describe, expect, it } from "vitest";

import {
  GENERATION_LOADING_STATUS,
  generationFormError,
  responseError,
} from "./generationUi";

const validForm = {
  subjectId: "1",
  pdfSelected: true,
  estimateReady: true,
  model: "anthropic/claude-haiku-5.5",
  sectionMode: "auto" as const,
  sectionName: "",
};

describe("generation UI state", () => {
  it("validates required form fields and manual section names", () => {
    expect(generationFormError(validForm)).toBeNull();
    expect(generationFormError({ ...validForm, pdfSelected: false })).toBe(
      "Select a lecture PDF",
    );
    expect(
      generationFormError({
        ...validForm,
        sectionMode: "manual",
        sectionName: "   ",
      }),
    ).toBe("Enter a manual section name");
  });

  it("describes every server-side loading phase", () => {
    expect(GENERATION_LOADING_STATUS).toContain("Extracting lecture");
    expect(GENERATION_LOADING_STATUS).toContain("generating questions");
    expect(GENERATION_LOADING_STATUS).toContain("validating result");
  });

  it("shows the structured backend stage and provider message", async () => {
    const error = await responseError(
      new Response(
        JSON.stringify({
          error: "openrouter_provider_error",
          message: "OpenRouter returned HTTP 400: schema is not supported",
          stage: "openrouter_request",
        }),
        { status: 502, headers: { "Content-Type": "application/json" } },
      ),
      "Question generation failed",
    );

    expect(error.message).toBe(
      "Generation failed during OpenRouter request.\n" +
        "OpenRouter returned HTTP 400: schema is not supported",
    );
  });

  it("keeps existing detail errors and a safe non-JSON fallback", async () => {
    await expect(
      responseError(
        new Response(JSON.stringify({ detail: "Upload a PDF file" }), {
          status: 415,
          headers: { "Content-Type": "application/json" },
        }),
        "Could not analyze the PDF",
      ),
    ).resolves.toEqual(new Error("Upload a PDF file"));
    await expect(
      responseError(
        new Response("proxy failed", { status: 502 }),
        "Question generation failed",
      ),
    ).resolves.toEqual(new Error("Question generation failed"));
  });
});
