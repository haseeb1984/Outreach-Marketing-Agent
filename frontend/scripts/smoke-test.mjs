import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";

const port = 3187;
const origin = `http://127.0.0.1:${port}`;
const server = spawn(process.execPath, ["node_modules/next/dist/bin/next", "start", "-p", String(port)], {
  cwd: process.cwd(),
  env: { ...process.env, NODE_ENV: "production", PORT: String(port) },
  stdio: ["ignore", "pipe", "pipe"],
});
let serverOutput = "";
server.stdout.on("data", (chunk) => { serverOutput += chunk.toString(); });
server.stderr.on("data", (chunk) => { serverOutput += chunk.toString(); });

const routes = [
  ["/", "Make every business conversation"],
  ["/features", "Platform capabilities"],
  ["/faq", "Frequently asked questions"],
  ["/login", "Sign in to your workspace"],
  ["/register", "Start with your workspace"],
  ["/privacy", "Privacy Policy"],
  ["/terms", "Terms of Use"],
  ["/contact", "Contact support"],
  ["/pricing", "Transparent plans. Server-verified access."],
  ["/how-it-works", "How it works"],
];

try {
  let ready = false;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    if (server.exitCode !== null) throw new Error(`Next.js server exited early.\n${serverOutput}`);
    try {
      const response = await fetch(origin);
      if (response.ok) { ready = true; break; }
    } catch {}
    await delay(500);
  }
  assert.equal(ready, true, `Next.js production server did not become ready.\n${serverOutput}`);

  for (const [route, expectedText] of routes) {
    const response = await fetch(new URL(route, origin));
    const html = await response.text();
    assert.equal(response.status, 200, `${route} returned HTTP ${response.status}`);
    assert.match(html, new RegExp(expectedText.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i"), `${route} missing expected page content`);
    assert.doesNotMatch(html, /Application error: a server-side exception has occurred/i, `${route} rendered a server exception`);
    console.log(`PASS ${route}`);
  }

  const privacy = await (await fetch(new URL("/privacy", origin))).text();
  assert.match(privacy, /name="robots" content="noindex, follow"/i, "Privacy page must remain noindex");
  const terms = await (await fetch(new URL("/terms", origin))).text();
  assert.match(terms, /name="robots" content="noindex, follow"/i, "Terms page must remain noindex");
  console.log("PASS privacy and terms noindex metadata");
} finally {
  server.kill("SIGTERM");
}
