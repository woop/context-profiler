import "@testing-library/jest-dom";
import { webcrypto } from "node:crypto";

if (!globalThis.crypto) {
  // jsdom environment may not expose Web Crypto; fall back to Node's webcrypto.
  Object.defineProperty(globalThis, "crypto", { value: webcrypto });
}
