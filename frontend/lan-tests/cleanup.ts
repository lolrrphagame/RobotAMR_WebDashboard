import { rmSync } from "node:fs";
export default function cleanup() {
  const directory = process.env.PBL4_LAN_TEST_DATA;
  if (directory) rmSync(directory, { recursive: true, force: true });
}
