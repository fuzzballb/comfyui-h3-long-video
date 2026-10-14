// Convert ComfyUI workflows with the real frontend in headless Chrome.
//   node convert.mjs ui2api <workflow.json> <out_api.json>
//   node convert.mjs api2ui <api.json> <out_workflow.json> [name]
// Needs ComfyUI running on 127.0.0.1:8188 and google-chrome-stable.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";

const [mode, input, output, name = "converted"] = process.argv.slice(2);
if (!["ui2api", "api2ui"].includes(mode) || !input || !output) {
  console.error("usage: convert.mjs ui2api|api2ui <in.json> <out.json> [name]");
  process.exit(2);
}
const data = fs.readFileSync(input, "utf8");
const port = 9333;
const profile = fs.mkdtempSync(path.join(os.tmpdir(), "comfy-headless-"));
const chrome = spawn("google-chrome-stable", ["--headless=new", "--disable-gpu", "--no-first-run",
  `--user-data-dir=${profile}`, `--remote-debugging-port=${port}`, "about:blank"], { stdio: "ignore" });

const sleep = ms => new Promise(r => setTimeout(r, ms));
let target;
for (let i = 0; i < 30 && !target; i++) {
  await sleep(500);
  target = await fetch(`http://127.0.0.1:${port}/json/new?http://127.0.0.1:8188/`, { method: "PUT" }).then(r => r.json()).catch(() => null);
}
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise(r => ws.onopen = r);
let id = 0;
const pending = new Map();
ws.onmessage = e => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
};
const send = (method, params = {}) => new Promise(r => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const evaluate = async expr => {
  const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
  if (r.result.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 800));
  return r.result.result.value;
};

for (let i = 0; i < 120; i++) {
  if (await evaluate("!!(window.app && window.app.graph && document.querySelector('canvas'))").catch(() => false)) break;
  await sleep(1000);
}
await sleep(5000); // let extensions finish registering widgets

const body = mode === "ui2api"
  ? `await app.loadGraphData(JSON.parse(${JSON.stringify(data)}), true, true, ${JSON.stringify(name)});
     await new Promise(r => setTimeout(r, 3000));
     const p = await app.graphToPrompt();
     return { result: p.output, missing: Object.entries(p.output).filter(([k, n]) => !n.class_type).map(([k]) => k) };`
  : `await app.loadApiJson(JSON.parse(${JSON.stringify(data)}), ${JSON.stringify(name)});
     await new Promise(r => setTimeout(r, 2000));
     app.graph.arrange(80);
     return { result: app.graph.serialize(), missing: [] };`;
const out = await evaluate(`(async () => { ${body} })()`);

let result = out.result;
if (mode === "api2ui") {
  // loadApiJson keeps string ids from the API prompt; the saved workflow needs integers
  let next = Math.max(0, ...result.nodes.map(n => n.id).filter(Number.isInteger)) + 1;
  const remap = {};
  for (const n of result.nodes) if (!Number.isInteger(n.id)) { remap[n.id] = next; n.id = next++; }
  for (const l of result.links) {
    if (Array.isArray(l)) { l[1] = remap[l[1]] ?? l[1]; l[3] = remap[l[3]] ?? l[3]; }
    else { l.origin_id = remap[l.origin_id] ?? l.origin_id; l.target_id = remap[l.target_id] ?? l.target_id; }
  }
  result.last_node_id = next - 1;
}
fs.writeFileSync(output, JSON.stringify(result));
console.log(`${mode}: ${mode === "ui2api" ? Object.keys(result).length : result.nodes.length} nodes -> ${output}` +
  (out.missing.length ? `; nodes without class_type: ${out.missing.join(",")}` : ""));

await send("Target.closeTarget", { targetId: target.id });
ws.close();
const exited = new Promise(r => chrome.once("exit", r));
chrome.kill();
await exited;
fs.rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
process.exit(0);
