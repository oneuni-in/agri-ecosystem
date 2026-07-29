import { check, sleep } from "k6";
import http from "k6/http";

/**
 * D30.D — browse load (the read surface an anonymous visitor actually hits).
 *
 * Read load/README.md before quoting any number from this: run locally it is a
 * RELATIVE BASELINE, not a production p95. What it does find is N+1 queries,
 * connection-pool exhaustion, and lock contention on the covers() keyset.
 */

const API = __ENV.API_BASE || "http://127.0.0.1:8000";

// 641001 is the seeded pincode (seed_e2e_milk.py); the rest are real Coimbatore
// pincodes from the D27 import. Spreading the load matters - hammering one
// pincode would sit in the query cache and measure nothing.
const PINCODES = ["641001", "641002", "641004", "641006", "641012", "641018"];

export const options = {
  scenarios: {
    browse: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 500 },
        { duration: "1m", target: 500 },
        { duration: "15s", target: 0 },
      ],
      gracefulRampDown: "10s",
    },
  },
  thresholds: {
    // A hard correctness bar: under load the app must not start erroring.
    http_req_failed: ["rate<0.01"],
    // Recorded, not asserted at a production number - see README.
    http_req_duration: ["p(95)<5000"],
  },
};

export default function () {
  const pincode = PINCODES[Math.floor(Math.random() * PINCODES.length)];

  const home = http.get(`${API}/catalog/milk/home/${pincode}`, {
    tags: { name: "milk_home" },
  });
  check(home, {
    "milk home 200": (r) => r.status === 200,
    "milk home has a scope": (r) => r.body && r.body.includes('"scope"'),
  });

  // Follow through to a vendor profile the way a real visitor does, so the
  // slug lookup and its joins are in the measurement too.
  if (home.status === 200) {
    const body = home.json();
    const vendors = (body && body.vendors) || [];
    if (vendors.length > 0) {
      const slug = vendors[Math.floor(Math.random() * vendors.length)].slug;
      const profile = http.get(`${API}/directory/businesses/${slug}`, {
        tags: { name: "business_profile" },
      });
      check(profile, {
        "profile 200": (r) => r.status === 200,
        // The reveal contract under load: a guest must never receive a number.
        "profile leaks no phone": (r) => !/\+91\d{10}/.test(r.body || ""),
      });
    }
  }

  http.get(`${API}/directory/covers/${pincode}`, { tags: { name: "covers" } });

  sleep(1);
}
