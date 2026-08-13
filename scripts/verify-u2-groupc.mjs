// U2 Group C — live binding checks against the dev stack (docker API :8000).
// Covers the cross-surface flows the console owns: a lead/need response
// reaching the consumer's my-needs list, and coverage-scoped inbox routing.
// The review-reply pending→approved lifecycle is proven exhaustively by
// tests/test_u2_review_replies.py (an automated spec, per U2's rule) and is
// not re-driven here.
import { spawnSync } from "node:child_process";

const API = process.env.API_URL ?? "http://127.0.0.1:8000";
const VENDOR = process.env.VENDOR_PHONE ?? "+919000000023";
const CONSUMER = process.env.CONSUMER_PHONE ?? "+919000000777";
const NONCE = `u2c${Date.now().toString(36)}`;

const results = [];
const record = (name, ok, detail = "") => {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
};

function resetThrottle(phone) {
  const digits = phone.replace("+", "");
  spawnSync("docker", [
    "exec", "agri-dev-redis-1", "redis-cli", "del",
    `otp:day:phone:${phone}`, `otp:cd:${phone}`, `otp:cdlvl:${phone}`,
    `otp:day:ip:172.19.0.1`, `otp:vday:ip:172.19.0.1`, `otp:phones:172.19.0.1`,
  ]);
  return digits;
}

function otpFromDockerLogs(phone) {
  const r = spawnSync("docker", ["logs", "agri-dev-api-1", "--tail", "200"], {
    encoding: "utf8", maxBuffer: 32 * 1024 * 1024,
  });
  const hay = `${r.stdout ?? ""}\n${r.stderr ?? ""}`;
  const m = [...hay.matchAll(new RegExp(`\\[mock-sms\\] to=${phone.replace("+", "\\+")} purpose=login code=(\\d{6})`, "g"))];
  if (!m.length) throw new Error(`no OTP for ${phone}`);
  return m[m.length - 1][1];
}

async function api(path, init = {}, sid = null) {
  const headers = { ...(init.headers ?? {}) };
  if (init.json !== undefined) {
    headers["content-type"] = "application/json";
    init.body = JSON.stringify(init.json);
  }
  if (sid) headers.cookie = `agri_sid=${sid}`;
  return fetch(`${API}${path}`, { ...init, headers });
}

async function login(phone) {
  resetThrottle(phone);
  const req = await api("/auth/otp/request", { method: "POST", json: { phone, purpose: "login" } });
  if (!req.ok) throw new Error(`otp request ${req.status} for ${phone}`);
  await new Promise((r) => setTimeout(r, 1500));
  const code = otpFromDockerLogs(phone);
  const verify = await api("/auth/otp/verify", { method: "POST", json: { phone, purpose: "login", code } });
  const { otp_proof } = await verify.json();
  const loginRes = await api("/auth/login", { method: "POST", json: { otp_proof } });
  const setCookie = loginRes.headers.getSetCookie?.() ?? [loginRes.headers.get("set-cookie")];
  const sid = setCookie.filter(Boolean).map((c) => /agri_sid=([^;]+)/.exec(c)).find(Boolean)?.[1];
  if (!sid) throw new Error(`no agri_sid for ${phone}`);
  // resolve a name for the new user so /leads/mine has a user (progressive account)
  return sid;
}

const vendorSid = await login(VENDOR);
const consumerSid = await login(CONSUMER);
console.log("logged in vendor + consumer");

// the vendor's fixture business + a pincode it covers
const bizList = await (await api("/directory/businesses?limit=50", {}, vendorSid)).json();
const biz = bizList.items.find((b) => b.slug === "e2e-milk-vendor") ?? bizList.items[0];
const detail = (await (await api(`/directory/businesses/${biz.slug}`)).json());
const coveredPincode = (detail.coverage_pincodes ?? ["641001"])[0];
console.log(`vendor business ${biz.slug}, covered pincode ${coveredPincode}`);

// ── need/lead → response → consumer my-needs ─────────────────────────────
// consumer posts a milk-subscription need targeting this business+pincode
const created = await api("/leads/inquiries", {
  method: "POST",
  json: {
    type: "milk_subscription",
    business_id: biz.id,
    pincode: coveredPincode,
    payload: { qty_liters: 2, milk_type: "cow", schedule: "daily", note: NONCE },
  },
}, consumerSid);
const inquiry = await created.json();
record("consumer posts a need in the vendor's covered pincode", created.status === 201, `inquiry ${inquiry.id ?? created.status}`);

// vendor sees it in the coverage-scoped inbox
const inbox = await (await api(`/leads/inbox?business_id=${biz.id}&type=milk_subscription&limit=50`, {}, vendorSid)).json();
const inInbox = (inbox.items ?? []).some((i) => i.id === inquiry.id);
record("vendor sees the need in the coverage-scoped inbox", inInbox);

// vendor responds
const responded = await api(`/leads/inquiries/${inquiry.id}/responses`, {
  method: "POST",
  json: { body: `We deliver in ${coveredPincode} — ${NONCE}` },
}, vendorSid);
record("vendor responds to the need", responded.status === 201);

// consumer's my-needs (/leads/mine) shows the response
const mine = await (await api("/leads/mine?limit=50", {}, consumerSid)).json();
const myRow = (mine.items ?? []).find((i) => i.id === inquiry.id);
const hasResponse = !!myRow && (myRow.responses ?? []).some((r) => r.body.includes(NONCE));
record("need response appears on the consumer's my-needs page (/leads/mine)", hasResponse);

// close it to keep the fixture tidy
await api(`/leads/inquiries/${inquiry.id}/close`, { method: "POST" }, vendorSid);

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} Group C checks passed`);
process.exit(failed.length ? 1 : 0);
