#!/usr/bin/env node
// Thin wrapper: the council is a stdlib-only Python script; npm only puts it on PATH.
"use strict";
const { spawnSync } = require("child_process");
const path = require("path");

const script = path.join(__dirname, "..", "skills", "llm-roundtable", "scripts", "roundtable.py");
const candidates = process.env.ROUNDTABLE_PYTHON
  ? [process.env.ROUNDTABLE_PYTHON]
  : process.platform === "win32" ? ["py", "python", "python3"] : ["python3", "python"];

for (const py of candidates) {
  const args = py === "py" ? ["-3", script, ...process.argv.slice(2)] : [script, ...process.argv.slice(2)];
  const r = spawnSync(py, args, { stdio: "inherit" });
  if (r.error && r.error.code === "ENOENT") continue;
  if (r.error) { console.error(r.error.message); process.exit(1); }
  if (r.signal) process.kill(process.pid, r.signal);
  process.exit(r.status === null ? 1 : r.status);
}
console.error("llm-roundtable needs Python 3.9+ on PATH (python3). Set ROUNDTABLE_PYTHON to use another interpreter.");
process.exit(1);
