import { describe, expect, it } from "vitest";
import { safeExternalUrl } from "@/lib/safe-external-url";

describe("E03 external listing URL validation", () => {
  it.each([
    "javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "file:///etc/passwd",
    "https://user:secret@example.com/",
    "https://example.com\\@attacker.invalid",
    "/relative/source",
    "not a url",
    "",
  ])("rejects unsafe URL %s", (value) => {
    expect(safeExternalUrl(value)).toBeNull();
  });

  it("rejects missing values", () => {
    expect(safeExternalUrl(undefined)).toBeNull();
    expect(safeExternalUrl(null)).toBeNull();
  });

  it("accepts normal HTTP(S) links", () => {
    expect(safeExternalUrl("https://example.com/listing?id=1")).toBe(
      "https://example.com/listing?id=1",
    );
    expect(safeExternalUrl("http://example.com/listing")).toBe("http://example.com/listing");
  });
});
