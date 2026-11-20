import { rmSync } from "node:fs";
export default function () {
  const path = process.env.PBL4_PRODUCTION_TEST_DATA;
  if (path) rmSync(path, { recursive: true, force: true });
}
