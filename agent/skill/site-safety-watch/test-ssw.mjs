import { readFileSync } from "node:fs";
// Run: node --test agent/skill/site-safety-watch/test-ssw.mjs
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { execFile } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const CLI = join(dirname(fileURLToPath(import.meta.url)), "ssw.mjs");

const EVENT = { id: 7, hazard: "blocked_exit", zone: "exit_a", status: "new" };
let pendingText = "NO_REPLY";
let escalationText = "NO_REPLY";
let newList = null; // override for GET /events?status=new
let resolvedPending = { text: "NO_REPLY" };
let requests = [];
let server;
let baseUrl;

before(async () => {
  server = createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      requests.push({ method: req.method, url: req.url, body: body ? JSON.parse(body) : null });
      const send = (code, data) => {
        res.writeHead(code, { "content-type": "application/json" });
        res.end(JSON.stringify(data));
      };
      const { pathname, searchParams } = new URL(req.url, "http://x");
      let m;
      if (req.method === "GET" && pathname === "/pending") return send(200, { text: pendingText });
      if (req.method === "GET" && pathname === "/resolved/pending") return send(200, resolvedPending);
      if (req.method === "GET" && pathname === "/stats")
        return send(200, { hours: Number(searchParams.get("hours") ?? 24), blocked_exit: 3, approved: 2, false_alarm: 1 });
      if (req.method === "GET" && pathname === "/digest")
        return send(200, { text: `Digest for the last ${searchParams.get("hours") ?? "24"} hours: 3 alerts.` });
      if (req.method === "GET" && pathname === "/escalations") return send(200, { text: escalationText });
      if (req.method === "GET" && pathname === "/events") {
        if (searchParams.get("status") === "new" && newList !== null) return send(200, newList);
        return send(200, [{ ...EVENT, status: searchParams.get("status") ?? "any" }]);
      }
      if ((m = pathname.match(/^\/events\/(\d+)(\/[\w-]+)?$/))) {
        const id = Number(m[1]);
        if (id === 404) return send(404, { error: "no such event" });
        if (id === 500) return send(500, { error: "boom" });
        const sub = m[2];
        if (req.method === "GET" && !sub) return send(200, { ...EVENT, id, rule: "29 CFR 1910.37" });
        if (req.method === "GET" && sub === "/alert") return send(200, { id, text: `Blocked exit at exit_a. Reply approve ${id}` });
        if (req.method === "POST" && sub === "/posted") return send(200, { ...EVENT, id, status: "posted" });
        if (req.method === "POST" && sub === "/resolved-announced") return send(200, { ...EVENT, id, status: "resolved" });
        if (req.method === "POST" && sub === "/disposition") {
          const p = JSON.parse(body);
          return send(200, { ...EVENT, id, status: p.disposition, disposition_by: p.by });
        }
      }
      send(404, { error: "not found" });
    });
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  baseUrl = `http://127.0.0.1:${server.address().port}`;
});

after(() => new Promise((r) => server.close(r)));

function run(args, env = {}) {
  return new Promise((resolve) => {
    execFile(process.execPath, [CLI, ...args], { env: { ...process.env, SSW_API_URL: baseUrl, ...env } }, (err, stdout, stderr) => {
      resolve({ code: err ? err.code : 0, stdout, stderr });
    });
  });
}

function last() {
  return requests.at(-1);
}

test("pending prints NO_REPLY raw", async () => {
  pendingText = "NO_REPLY";
  const r = await run(["pending"]);
  assert.equal(r.code, 0);
  assert.equal(r.stdout, "NO_REPLY\n");
  assert.deepEqual(last(), { method: "GET", url: "/pending", body: null });
});

test("pending prints a summary raw, not JSON", async () => {
  pendingText = "1 new event: 7 blocked_exit exit_a";
  const r = await run(["pending"]);
  assert.equal(r.code, 0);
  assert.equal(r.stdout, "1 new event: 7 blocked_exit exit_a\n");
});

test("events without filter", async () => {
  const r = await run(["events"]);
  assert.equal(r.code, 0);
  assert.equal(last().url, "/events");
  assert.equal(JSON.parse(r.stdout)[0].id, 7);
});

test("events --status new", async () => {
  const r = await run(["events", "--status", "new"]);
  assert.equal(r.code, 0);
  assert.equal(last().url, "/events?status=new");
  assert.equal(JSON.parse(r.stdout)[0].status, "new");
});

test("event <id>", async () => {
  const r = await run(["event", "12"]);
  assert.equal(r.code, 0);
  assert.deepEqual(last(), { method: "GET", url: "/events/12", body: null });
  assert.equal(JSON.parse(r.stdout).rule, "29 CFR 1910.37");
});

test("alert <id>", async () => {
  const r = await run(["alert", "12"]);
  assert.equal(r.code, 0);
  assert.equal(last().url, "/events/12/alert");
  assert.match(JSON.parse(r.stdout).text, /approve 12/);
});

test("posted <id>", async () => {
  const r = await run(["posted", "12"]);
  assert.equal(r.code, 0);
  assert.equal(last().method, "POST");
  assert.equal(last().url, "/events/12/posted");
  assert.equal(JSON.parse(r.stdout).status, "posted");
});

test("dispose approved", async () => {
  const r = await run(["dispose", "12", "approved", "--by", "U0123ABC"]);
  assert.equal(r.code, 0);
  assert.deepEqual(last(), { method: "POST", url: "/events/12/disposition", body: { disposition: "approved", by: "U0123ABC" } });
  const out = JSON.parse(r.stdout);
  assert.equal(out.status, "approved");
  assert.equal(out.disposition_by, "U0123ABC");
});

test("dispose false_alarm", async () => {
  const r = await run(["dispose", "12", "false_alarm", "--by", "U9"]);
  assert.equal(r.code, 0);
  assert.deepEqual(last().body, { disposition: "false_alarm", by: "U9" });
});

test("bad input exits 2 with usage and makes no request", async () => {
  const cases = [
    [],
    ["nope"],
    ["pending", "extra"],
    ["event"],
    ["event", "12a"],
    ["event", "-1"],
    ["alert", "../x"],
    ["posted", "1", "2"],
    ["events", "--status", "bogus"],
    ["events", "--state", "new"],
    ["dispose", "12", "approve", "--by", "U1"],
    ["dispose", "12", "false-alarm", "--by", "U1"],
    ["dispose", "12", "approved"],
    ["dispose", "12", "approved", "--who", "U1"],
    ["dispose", "x", "approved", "--by", "U1"],
  ];
  for (const args of cases) {
    const before = requests.length;
    const r = await run(args);
    assert.equal(r.code, 2, `args ${JSON.stringify(args)}`);
    assert.match(r.stderr, /usage: node ssw\.mjs/, `args ${JSON.stringify(args)}`);
    assert.equal(r.stdout, "");
    assert.equal(requests.length, before, `args ${JSON.stringify(args)} made a request`);
  }
});

test("non-2xx exits 1 with a one-line error", async () => {
  for (const id of ["404", "500"]) {
    const r = await run(["event", id]);
    assert.equal(r.code, 1);
    assert.equal(r.stdout, "");
    assert.match(r.stderr, new RegExp(`^error: API returned ${id} `));
    assert.equal(r.stderr.trim().split("\n").length, 1);
  }
});

test("unreachable API exits 1 with a one-line error", async () => {
  const probe = createServer();
  await new Promise((r) => probe.listen(0, "127.0.0.1", r));
  const port = probe.address().port;
  await new Promise((r) => probe.close(r));
  const r = await run(["pending"], { SSW_API_URL: `http://127.0.0.1:${port}` });
  assert.equal(r.code, 1);
  assert.match(r.stderr, /^error: API unreachable at /);
  assert.equal(r.stderr.trim().split("\n").length, 1);
});

test("falls back to config.json when SSW_API_URL is unset", async () => {
  const env = { ...process.env };
  delete env.SSW_API_URL;
  const r = await new Promise((resolve) => {
    execFile(process.execPath, [CLI, "event", "1"], { env }, (err, stdout, stderr) => resolve({ code: err ? err.code : 0, stderr }));
  });
  // config.json points at the deployed API address, which nothing serves in this test
  const { apiUrl } = JSON.parse(readFileSync(new URL("./config.json", import.meta.url), "utf8"));
  assert.equal(r.code, 1);
  assert.ok(r.stderr.includes(new URL(apiUrl).host), r.stderr);
});

test("post-new prints each new alert and marks it posted", async () => {
  newList = [{ ...EVENT, id: 9 }, { ...EVENT, id: 7 }];
  requests = [];
  const r = await run(["post-new"]);
  newList = null;
  assert.equal(r.code, 0);
  assert.equal(r.stdout, "Blocked exit at exit_a. Reply approve 7\n\nBlocked exit at exit_a. Reply approve 9\n");
  assert.deepEqual(requests.map((q) => `${q.method} ${q.url}`), [
    "GET /events?status=new",
    "GET /events/7/alert",
    "POST /events/7/posted",
    "GET /events/9/alert",
    "POST /events/9/posted",
  ]);
});

test("post-new prints NO_REPLY and posts nothing when there is nothing new", async () => {
  newList = [];
  requests = [];
  const r = await run(["post-new"]);
  newList = null;
  assert.equal(r.code, 0);
  assert.equal(r.stdout, "NO_REPLY\n");
  assert.deepEqual(requests.map((q) => `${q.method} ${q.url}`), ["GET /events?status=new"]);
});

test("stats prints JSON, with and without --hours", async () => {
  let r = await run(["stats"]);
  assert.equal(r.code, 0);
  assert.deepEqual(last(), { method: "GET", url: "/stats", body: null });
  assert.equal(JSON.parse(r.stdout).blocked_exit, 3);
  r = await run(["stats", "--hours", "168"]);
  assert.equal(r.code, 0);
  assert.equal(last().url, "/stats?hours=168");
  assert.equal(JSON.parse(r.stdout).hours, 168);
});

test("digest prints .text raw", async () => {
  let r = await run(["digest"]);
  assert.equal(r.code, 0);
  assert.equal(last().url, "/digest");
  assert.equal(r.stdout, "Digest for the last 24 hours: 3 alerts.\n");
  r = await run(["digest", "--hours", "8"]);
  assert.equal(last().url, "/digest?hours=8");
  assert.equal(r.stdout, "Digest for the last 8 hours: 3 alerts.\n");
});

test("escalate prints NO_REPLY or the escalation text raw", async () => {
  escalationText = "NO_REPLY";
  let r = await run(["escalate"]);
  assert.equal(r.code, 0);
  assert.equal(last().url, "/escalations");
  assert.equal(r.stdout, "NO_REPLY\n");
  escalationText = "Event 7 has waited 15 min for a decision.";
  r = await run(["escalate", "--after-min", "15"]);
  assert.equal(r.code, 0);
  assert.equal(last().url, "/escalations?after_min=15");
  assert.equal(r.stdout, "Event 7 has waited 15 min for a decision.\n");
});

test("stats, digest and escalate reject bad input with exit 2", async () => {
  const cases = [
    ["stats", "--hours"],
    ["stats", "--hours", "0"],
    ["stats", "--hours", "-3"],
    ["stats", "--hours", "1.5"],
    ["stats", "--hours", "24h"],
    ["stats", "--hours", "007"],
    ["stats", "--days", "1"],
    ["stats", "24"],
    ["digest", "--hours", "abc"],
    ["digest", "--after-min", "5"],
    ["escalate", "--after-min", "0"],
    ["escalate", "--hours", "5"],
    ["escalate", "--after-min", "5", "extra"],
  ];
  for (const args of cases) {
    const before = requests.length;
    const r = await run(args);
    assert.equal(r.code, 2, `args ${JSON.stringify(args)}`);
    assert.match(r.stderr, /usage: node ssw\.mjs/, `args ${JSON.stringify(args)}`);
    assert.equal(r.stdout, "");
    assert.equal(requests.length, before, `args ${JSON.stringify(args)} made a request`);
  }
});

test("post-resolved posts the all-clear and marks each event announced", async () => {
  resolvedPending = { text: "*Exit cleared*: event 4 ... Measured: 48 s from first sighting to clear.", event_ids: [4] };
  requests = [];
  const r = await run(["post-resolved"]);
  resolvedPending = { text: "NO_REPLY" };
  assert.equal(r.code, 0);
  assert.match(r.stdout, /Exit cleared/);
  assert.deepEqual(requests.map((q) => `${q.method} ${q.url}`), ["GET /resolved/pending", "POST /events/4/resolved-announced"]);
});

test("post-resolved prints NO_REPLY when nothing cleared", async () => {
  requests = [];
  const r = await run(["post-resolved"]);
  assert.equal(r.code, 0);
  assert.equal(r.stdout, "NO_REPLY\n");
  assert.deepEqual(requests.map((q) => `${q.method} ${q.url}`), ["GET /resolved/pending"]);
});
