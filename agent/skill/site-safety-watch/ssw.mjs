#!/usr/bin/env node
// Site Safety Watch CLI for the OpenClaw agent. Node 22 built-ins only.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_URL = "http://127.0.0.1:8100";
const TIMEOUT_MS = 10_000;
const DISPOSITIONS = ["approved", "false_alarm"];
const STATUSES = ["new", "posted", "approved", "false_alarm"];

const USAGE = [
  "usage: node ssw.mjs pending",
  "       node ssw.mjs events [--status new|posted|approved|false_alarm]",
  "       node ssw.mjs event <id>",
  "       node ssw.mjs alert <id>",
  "       node ssw.mjs posted <id>",
  "       node ssw.mjs dispose <id> approved|false_alarm --by <slack_user_id>",
  "       node ssw.mjs post-new",
  "       node ssw.mjs post-resolved",
  "       node ssw.mjs stats [--hours N]",
  "       node ssw.mjs digest [--hours N]",
  "       node ssw.mjs escalate [--after-min N]",
].join("\n");

function usage(msg) {
  if (msg) process.stderr.write(`error: ${msg}\n`);
  process.stderr.write(USAGE + "\n");
  process.exit(2);
}

function fail(msg) {
  process.stderr.write(`error: ${msg.replace(/\s+/g, " ").trim()}\n`);
  process.exit(1);
}

function baseUrl() {
  if (process.env.SSW_API_URL) return process.env.SSW_API_URL;
  try {
    const here = dirname(fileURLToPath(import.meta.url));
    const cfg = JSON.parse(readFileSync(join(here, "config.json"), "utf8"));
    if (typeof cfg.apiUrl === "string" && cfg.apiUrl) return cfg.apiUrl;
  } catch {
    // no usable config.json, fall through to the default
  }
  return DEFAULT_URL;
}

function checkId(id) {
  if (id === undefined || !/^\d+$/.test(id)) usage(`event id must be digits only, got ${JSON.stringify(id ?? "")}`);
  return id;
}

// Parses an optional single "<flag> N" pair; N must be a positive integer.
function optionalCount(cmd, rest, flag) {
  if (rest.length === 0) return null;
  if (rest.length !== 2 || rest[0] !== flag) usage(`${cmd} takes only ${flag} N`);
  if (!/^[1-9]\d{0,5}$/.test(rest[1])) usage(`${flag} must be a positive integer, got ${JSON.stringify(rest[1])}`);
  return rest[1];
}

async function printText(path) {
  const data = await call("GET", path);
  if (typeof data?.text !== "string") fail(`API ${path.split("?")[0]} response has no text field`);
  process.stdout.write(data.text + "\n");
}

async function call(method, path, body) {
  const url = baseUrl().replace(/\/+$/, "") + path;
  let res;
  try {
    res = await fetch(url, {
      method,
      headers: body ? { "content-type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch (err) {
    const why = err?.name === "TimeoutError" ? `timed out after ${TIMEOUT_MS / 1000} s` : (err?.cause?.code || err?.message || String(err));
    fail(`API unreachable at ${url}: ${why}`);
  }
  const text = await res.text();
  if (!res.ok) fail(`API returned ${res.status} for ${method} ${path}: ${text.slice(0, 200)}`);
  try {
    return JSON.parse(text);
  } catch {
    fail(`API returned non-JSON for ${method} ${path}: ${text.slice(0, 200)}`);
  }
}

function print(data) {
  process.stdout.write(JSON.stringify(data) + "\n");
}

async function main(argv) {
  const [cmd, ...rest] = argv;
  switch (cmd) {
    case "pending": {
      if (rest.length) usage("pending takes no arguments");
      const data = await call("GET", "/pending");
      if (typeof data?.text !== "string") fail("API /pending response has no text field");
      process.stdout.write(data.text + "\n");
      return;
    }
    case "events": {
      let path = "/events";
      if (rest.length) {
        if (rest.length !== 2 || rest[0] !== "--status") usage("events takes only --status <value>");
        if (!STATUSES.includes(rest[1])) usage(`status must be one of ${STATUSES.join(", ")}`);
        path += `?status=${encodeURIComponent(rest[1])}`;
      }
      print(await call("GET", path));
      return;
    }
    case "event":
    case "alert":
    case "posted": {
      if (rest.length !== 1) usage(`${cmd} takes exactly one event id`);
      const id = checkId(rest[0]);
      if (cmd === "event") print(await call("GET", `/events/${id}`));
      else if (cmd === "alert") print(await call("GET", `/events/${id}/alert`));
      else print(await call("POST", `/events/${id}/posted`));
      return;
    }
    case "dispose": {
      if (rest.length !== 4 || rest[2] !== "--by") usage("dispose takes <id> <disposition> --by <slack_user_id>");
      const id = checkId(rest[0]);
      const disposition = rest[1];
      if (!DISPOSITIONS.includes(disposition)) usage(`disposition must be one of ${DISPOSITIONS.join(", ")}`);
      const by = rest[3].trim();
      if (!by) usage("--by needs a Slack user id");
      print(await call("POST", `/events/${id}/disposition`, { disposition, by }));
      return;
    }
    case "post-resolved": {
      // Scheduled command job (no model call): post the all-clear for events the camera
      // confirmed clear, then mark each announced so it posts once. NO_REPLY when none.
      if (rest.length) usage("post-resolved takes no arguments");
      const data = await call("GET", "/resolved/pending");
      if (typeof data?.text !== "string") fail("API /resolved/pending response has no text field");
      if (data.text === "NO_REPLY") {
        process.stdout.write("NO_REPLY\n");
        return;
      }
      for (const id of data.event_ids || []) {
        await call("POST", `/events/${checkId(String(id))}/resolved-announced`);
      }
      process.stdout.write(data.text + "\n");
      return;
    }
    case "post-new": {
      // For the scheduled check (an OpenClaw command job, no model call): print the alert
      // text of every new event and mark it posted, or NO_REPLY when there is nothing new.
      if (rest.length) usage("post-new takes no arguments");
      const events = await call("GET", "/events?status=new");
      if (!Array.isArray(events)) fail("API /events response is not a list");
      if (events.length === 0) {
        process.stdout.write("NO_REPLY\n");
        return;
      }
      const texts = [];
      for (const ev of [...events].sort((a, b) => a.id - b.id)) {
        const id = checkId(String(ev.id));
        const alert = await call("GET", `/events/${id}/alert`);
        if (typeof alert?.text !== "string") fail(`API alert for event ${id} has no text field`);
        texts.push(alert.text);
        await call("POST", `/events/${id}/posted`);
      }
      process.stdout.write(texts.join("\n\n") + "\n");
      return;
    }
    case "stats":
    case "digest": {
      const hours = optionalCount(cmd, rest, "--hours");
      const path = `/${cmd}` + (hours ? `?hours=${hours}` : "");
      if (cmd === "stats") print(await call("GET", path));
      else await printText(path);
      return;
    }
    case "escalate": {
      const afterMin = optionalCount(cmd, rest, "--after-min");
      await printText("/escalations" + (afterMin ? `?after_min=${afterMin}` : ""));
      return;
    }
    case undefined:
    case "-h":
    case "--help":
      usage();
    default:
      usage(`unknown command ${JSON.stringify(cmd)}`);
  }
}

await main(process.argv.slice(2));
