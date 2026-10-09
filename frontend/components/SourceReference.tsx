export type SourceDocumentReference = {
  id: number;
  filename: string;
};

export function sourceFileHref(
  sourceDocumentId: number,
  sourcePage?: string | number | null,
): string {
  const pageMatch = sourcePage == null ? null : String(sourcePage).match(/\d+/);
  const pageFragment = pageMatch && Number(pageMatch[0]) > 0
    ? `#page=${pageMatch[0]}`
    : "";
  return `/api/lecture-sources/${sourceDocumentId}/file${pageFragment}`;
}

export function SourceReference({
  sourceDocument,
  sourcePage,
  sourceText,
  compact = false,
}: {
  sourceDocument?: SourceDocumentReference | null;
  sourcePage?: string | number | null;
  sourceText?: string | null;
  compact?: boolean;
}) {
  const filename = sourceDocument?.filename || sourceText;
  if (!filename) return null;

  return (
    <div className={compact ? "source-reference compact-source" : "source-reference"}>
      <span>Source: {filename}{sourcePage != null && <> · Page {sourcePage}</>}</span>
      {sourceDocument && (
        <a
          href={sourceFileHref(sourceDocument.id, sourcePage)}
          rel="noreferrer"
          target="_blank"
        >
          Open source
        </a>
      )}
    </div>
  );
}
