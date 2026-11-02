import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Vitest globals are off (explicit imports keep tests greppable), so Testing Library's auto-cleanup needs wiring.
afterEach(() => {
  cleanup();
});
