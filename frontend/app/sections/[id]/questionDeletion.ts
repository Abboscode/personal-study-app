import type { SectionQuestion } from "@/components/SectionQuestionList";

type DeleteRequest = (
  input: string,
  init?: RequestInit,
) => Promise<Response>;

export async function deleteQuestionRequest(
  questionId: number,
  request: DeleteRequest = fetch,
): Promise<void> {
  const response = await request(`/api/questions/${questionId}`, {
    method: "DELETE",
  });
  if (response.ok) return;

  let message = "Could not delete the question";
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object") {
      const detail = (body as Record<string, unknown>).detail;
      if (typeof detail === "string" && detail.trim()) message = detail;
    }
  } catch {
    // Keep the safe fallback for non-JSON responses.
  }
  throw new Error(message);
}

export function withoutQuestion(
  questions: readonly SectionQuestion[],
  questionId: number,
): SectionQuestion[] {
  return questions.filter((question) => question.id !== questionId);
}
