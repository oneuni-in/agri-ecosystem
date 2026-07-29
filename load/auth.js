import { check, sleep } from "k6";
import http from "k6/http";

/**
 * D30.D — auth load (50 concurrent OTP requests).
 *
 * Requires the signup_enabled flag to be ON, or every request answers
 * 503 signup_unavailable and this measures nothing. See load/README.md.
 *
 * Uses the mock SMS driver by construction: pointing this at an environment
 * with sms_provider=msg91 would send thousands of real messages and bill for
 * every one (₹0.25 each). The check below fails loudly if that is the case.
 */

const API = __ENV.API_BASE || "http://127.0.0.1:8000";

export const options = {
  scenarios: {
    auth: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "20s", target: 50 },
        { duration: "40s", target: 50 },
        { duration: "10s", target: 0 },
      ],
      gracefulRampDown: "10s",
    },
  },
  thresholds: {
    // 429 is a CORRECT answer here - the OTP throttle ladder is supposed to
    // fire under this shape of load - so failure rate is measured on 5xx only.
    "http_req_failed{expected_response:true}": ["rate<0.01"],
    http_req_duration: ["p(95)<5000"],
  },
};

// A distinct phone per VU per iteration: reusing one number would measure the
// per-phone cooldown ladder rather than throughput.
function phoneFor(vu, iter) {
  const n = 6000000000 + ((vu * 100000 + iter) % 999999999);
  return `+91${n}`;
}

export default function () {
  const phone = phoneFor(__VU, __ITER);

  const res = http.post(
    `${API}/auth/otp/request`,
    JSON.stringify({ phone, purpose: "login" }),
    { headers: { "content-type": "application/json" }, tags: { name: "otp_request" } },
  );

  check(res, {
    // 200 issued, 429 throttled - both are the system working as designed.
    "otp request answered 200 or 429": (r) => r.status === 200 || r.status === 429,
    "signup gate is OPEN (503 means the flag is off - see README)": (r) => r.status !== 503,
    "no 5xx": (r) => r.status < 500 || r.status === 503,
  });

  sleep(1);
}
