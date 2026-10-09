import { describe, expect, it, vi } from "vitest";

import type { SectionQuestion } from "@/components/SectionQuestionList";

import { deleteQuestionRequest, withoutQuestion } from "./questionDeletion";

const questions = [
  { id: 7, question: "First" },
  { id: 8, question: "Second" },
] as SectionQuestion[];

describe("question deletion", () => {
  it("sends DELETE to the existing question endpoint", async () => {
    const request = vi.fn(async () => new Response(null, { status: 204 }));

    await deleteQuestionRequest(7, request);

    expect(request).toHaveBeenCalledWith("/api/questions/7", {
      method: "DELETE",
    });
  });

  it("reports backend errors without removing the question", async () => {
    const request = vi.fn(async () =>
      new Response(JSON.stringify({ detail: "Question not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(deleteQuestionRequest(99, request)).rejects.toThrow(
      "Question not found",
    );
    expect(withoutQuestion(questions, 99)).toEqual(questions);
  });

  it("removes only the deleted question from local section state", () => {
    expect(withoutQuestion(questions, 7).map((question) => question.id)).toEqual([8]);
  });
});
