import { describe, expect, it } from "vitest";

import { onlyJsonFiles } from "./importFiles";

describe("onlyJsonFiles", () => {
  it("keeps JSON files from a folder and ignores unrelated files", () => {
    const files = [
      { name: "memory.json" },
      { name: "SRAM.JSON" },
      { name: "notes.txt" },
      { name: ".DS_Store" },
      { name: "diagram.png" },
    ];

    expect(onlyJsonFiles(files).map((file) => file.name)).toEqual([
      "memory.json",
      "SRAM.JSON",
    ]);
  });
});

