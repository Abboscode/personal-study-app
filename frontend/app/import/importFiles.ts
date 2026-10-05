export function onlyJsonFiles<T extends { name: string }>(files: Iterable<T>): T[] {
  return Array.from(files).filter((file) => file.name.toLowerCase().endsWith(".json"));
}

