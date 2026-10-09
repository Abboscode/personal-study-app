export type GenerationSubject = {
  id: number;
  name: string;
};

export function SubjectSelector({
  subjects,
  value,
  onChange,
}: {
  subjects: GenerationSubject[];
  value: string;
  onChange: (subjectId: string) => void;
}) {
  return (
    <label className="field-group">
      <span>Subject</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {subjects.map((subject) => (
          <option key={subject.id} value={subject.id}>{subject.name}</option>
        ))}
      </select>
    </label>
  );
}
