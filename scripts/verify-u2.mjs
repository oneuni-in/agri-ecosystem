// U2 Group B — live binding-proof mutation checks, run against the dev stack
// (docker API :8000, web-milk :3000). Every check mutates through the SAME
// owner API the console uses (agri_sid session, the scripted-session recipe)
// and asserts on the PUBLIC read — API for the immediate ones, the real
// consumer page for the price check (300s cache window, U1 §5e precedent).
//
// Usage: node scripts/verify-u2.mjs            (full run, includes ~5min wait)
//        SKIP_PAGE_CHECK=1 node scripts/verify-u2.mjs   (API-level only)
import { spawnSync } from "node:child_process";

const API = process.env.API_URL ?? "http://127.0.0.1:8000";
const MILK = process.env.MILK_URL ?? "http://localhost:3000";
const PHONE = process.env.VENDOR_PHONE ?? "+919000000023";
const NONCE = `u2v${Date.now().toString(36)}`;

const results = [];
function record(name, ok, detail = "") {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
}

function otpFromDockerLogs(phone) {
  const r = spawnSync("docker", ["logs", "agri-dev-api-1", "--tail", "200"], {
    encoding: "utf8",
    maxBuffer: 32 * 1024 * 1024,
  });
  const hay = `${r.stdout ?? ""}\n${r.stderr ?? ""}`;
  const matches = [
    ...hay.matchAll(
      new RegExp(`\\[mock-sms\\] to=${phone.replace("+", "\\+")} purpose=login code=(\\d{6})`, "g"),
    ),
  ];
  if (!matches.length) throw new Error(`no mock-sms OTP for ${phone}`);
  return matches[matches.length - 1][1];
}

async function api(path, init = {}, sid = null) {
  const headers = { ...(init.headers ?? {}) };
  if (init.json !== undefined) {
    headers["content-type"] = "application/json";
    init.body = JSON.stringify(init.json);
  }
  if (sid) headers.cookie = `agri_sid=${sid}`;
  const res = await fetch(`${API}${path}`, { ...init, headers });
  return res;
}

async function login(phone) {
  const requested = await api("/auth/otp/request", {
    method: "POST",
    json: { phone, purpose: "login" },
  });
  if (!requested.ok) throw new Error(`otp request ${requested.status} (5/day throttle? clear otp:* keys in dev redis)`);
  await new Promise((r) => setTimeout(r, 1500));
  const code = otpFromDockerLogs(phone);
  const verify = await api("/auth/otp/verify", {
    method: "POST",
    json: { phone, purpose: "login", code },
  });
  if (!verify.ok) throw new Error(`otp verify ${verify.status}`);
  const { otp_proof } = await verify.json();
  const loginRes = await api("/auth/login", { method: "POST", json: { otp_proof } });
  if (!loginRes.ok) throw new Error(`login ${loginRes.status}`);
  const setCookie = loginRes.headers.getSetCookie?.() ?? [loginRes.headers.get("set-cookie")];
  const sid = setCookie
    .filter(Boolean)
    .map((c) => /agri_sid=([^;]+)/.exec(c))
    .find(Boolean)?.[1];
  if (!sid) throw new Error("no agri_sid cookie in login response");
  return sid;
}

// A tiny valid PNG (1x1 white) — enough for shared.media.reencode_image.
const PNG_1PX = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

const sid = await login(PHONE);
console.log(`logged in as ${PHONE}`);

// ── pick the fixture business ────────────────────────────────────────────
const bizList = await (await api("/directory/businesses?limit=50", {}, sid)).json();
const biz = bizList.items.find((b) => b.slug === "e2e-milk-vendor") ?? bizList.items[0];
if (!biz) throw new Error("vendor owns no businesses — seed_e2e_milk.py not run?");
console.log(`business: ${biz.name} (${biz.slug})`);

// ── 4. price edit FIRST (its page assertion polls a 300s cache) ──────────
const myProducts = await (
  await api(`/catalog/my/products?business_id=${biz.id}&limit=50`, {}, sid)
).json();
const product = myProducts.items.find((p) => p.status === "active") ?? myProducts.items[0];
if (!product) throw new Error("fixture has no products");
const priorPrice = product.price_display;
const newPrice = `₹61/L ${NONCE}`;
{
  const res = await api(`/catalog/products/${product.id}`, {
    method: "PATCH",
    json: { price_display: newPrice },
  }, sid);
  record("price edit accepted (owner PATCH)", res.ok, `${product.name} → ${newPrice}`);
}
const priceCheckStarted = Date.now();

// ── 1. profile edit → public business page ───────────────────────────────
{
  // the public detail nests the business under `.business`
  const detailBefore = (await (await api(`/directory/businesses/${biz.slug}`)).json()).business;
  const priorDescription = detailBefore.description;
  const newDescription = { ...(priorDescription ?? {}), en: `Fresh milk daily — ${NONCE}` };
  const res = await api(`/directory/businesses/${biz.id}`, {
    method: "PATCH",
    json: { description: newDescription },
  }, sid);
  const pub = (await (await api(`/directory/businesses/${biz.slug}`)).json()).business;
  record(
    "profile edit → public business page reflects it",
    res.ok && pub.description?.en?.includes(NONCE),
    `public description.en now carries ${NONCE}`,
  );
  await api(`/directory/businesses/${biz.id}`, {
    method: "PATCH",
    json: { description: priorDescription },
  }, sid); // restore
}

// ── 2. coverage pincode added → covers() blend ───────────────────────────
{
  const detail = await (await api(`/directory/businesses/${biz.slug}`)).json();
  const prior = detail.coverage_pincodes ?? [];
  const added = "641011";
  if (prior.includes(added)) {
    record("coverage pincode added → covers() blend", false, `${added} already covered — pick another`);
  } else {
    await api(`/directory/businesses/${biz.id}/coverage`, {
      method: "PUT",
      json: { pincodes: [...prior, added] },
    }, sid);
    const covers = await (await api(`/directory/covers/${added}?limit=100`)).json();
    const present = (covers.items ?? []).some((row) => row.slug === biz.slug);
    record("coverage pincode added → business appears in that pincode's covers() blend", present, `${biz.slug} in /directory/covers/${added}`);
    await api(`/directory/businesses/${biz.id}/coverage`, {
      method: "PUT",
      json: { pincodes: prior },
    }, sid); // restore
  }
}

// ── 3. media upload → public page · bad file type → refused server-side ──
{
  const form = new FormData();
  form.append("file", new Blob([PNG_1PX], { type: "image/png" }), "u2.png");
  const up = await api(`/catalog/products/${product.id}/images`, { method: "POST", body: form }, sid);
  const pubProducts = await (await api(`/catalog/businesses/${biz.slug}/products?limit=50`)).json();
  const pubRow = (pubProducts.items ?? []).find((p) => p.id === product.id);
  const served = up.ok && pubRow && pubRow.images.length > 0;
  record(
    "media upload → renders on the public page",
    Boolean(served),
    served ? `public images[0] = ${pubRow.images[pubRow.images.length - 1]}` : `upload ${up.status}`,
  );
  if (up.ok) {
    const body = await up.json();
    await api(`/catalog/products/${product.id}/images/${body.images.length - 1}`, { method: "DELETE" }, sid); // restore
  }

  const badForm = new FormData();
  badForm.append("file", new Blob([Buffer.from("not an image")], { type: "text/plain" }), "evil.txt");
  const bad = await api(`/catalog/products/${product.id}/images`, { method: "POST", body: badForm }, sid);
  record("rejected file type is refused server-side", bad.status === 422, `POST text/plain → ${bad.status}`);
}

// ── 5. soft delete: scratch business+product vanish publicly ─────────────
{
  const created = await (
    await api("/directory/businesses", {
      method: "POST",
      json: { name: `U2 Scratch Dairy ${NONCE}`, type: "vendor", primary_pincode: "641001" },
    }, sid)
  ).json();
  const scratchProduct = await (
    await api(`/catalog/businesses/${created.id}/products`, {
      method: "POST",
      json: {
        vertical_slug: "milk",
        name: `U2 Scratch Milk ${NONCE}`,
        specs: { category: "milk", milk_type: "cow" },
        price_display: "₹50/L",
      },
    }, sid)
  ).json();

  const delProduct = await api(`/catalog/products/${scratchProduct.id}`, { method: "DELETE" }, sid);
  const productGone = (await api(`/catalog/products/${scratchProduct.slug}`)).status === 404;
  record("product soft-deleted → public product page 404s", delProduct.status === 204 && productGone);

  const delBiz = await api(`/directory/businesses/${created.id}`, { method: "DELETE" }, sid);
  const bizGone = (await api(`/directory/businesses/${created.slug}`)).status === 404;
  const list = await (await api("/directory/businesses?limit=50", {}, sid)).json();
  const outOfList = !list.items.some((b) => b.id === created.id);
  record(
    "listing soft-deleted → vanishes from public + owner list (row survives, per pytest include_deleted proof)",
    delBiz.status === 204 && bizGone && outOfList,
  );
}

// ── 4b. the consumer results card shows the new price (real page) ────────
if (process.env.SKIP_PAGE_CHECK) {
  console.log("SKIP_PAGE_CHECK set — price page assertion skipped (API PATCH verified above).");
} else {
  const deadline = priceCheckStarted + 360_000;
  let seen = false;
  let url = `${MILK}/en/coimbatore/641001`;
  while (Date.now() < deadline && !seen) {
    const res = await fetch(url, { redirect: "follow" });
    const html = await res.text();
    if (html.includes(NONCE)) seen = true;
    else await new Promise((r) => setTimeout(r, 15_000));
  }
  record(
    "listing price edit → the consumer results card changes (U1b surface)",
    seen,
    seen ? `${url} shows "${newPrice}" after the cache window` : `not seen within 6min on ${url}`,
  );
}

// restore the price
await api(`/catalog/products/${product.id}`, {
  method: "PATCH",
  json: { price_display: priorPrice },
}, sid);
console.log("price restored:", priorPrice);

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
process.exit(failed.length ? 1 : 0);
