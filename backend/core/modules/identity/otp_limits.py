"""Every OTP limit lives here (D07.C) - the numbers the test suite proves.

Change a value and a boundary test in tests/test_otp_throttle.py or
tests/test_otp_service.py MUST change with it; the suite pins the numbers,
not the intent. Nothing in this file is read from the environment on purpose:
these are product security decisions, not deployment knobs.
"""

# --- code shape -------------------------------------------------------------
OTP_CODE_LENGTH = 6
OTP_TTL_SECONDS = 300  # 5 minutes
OTP_MAX_ATTEMPTS = 3  # wrong tries before the code burns

# --- resend cooldown (per phone) ---------------------------------------------
# Escalates per issue within the reset window: 1st reissue waits 30s, next 60s,
# then 300s for every subsequent one. A quiet hour resets the ladder.
RESEND_COOLDOWNS_SECONDS = (30, 60, 300)
RESEND_ESCALATION_RESET_SECONDS = 3600

# --- daily issue caps (fixed 24h windows) ------------------------------------
OTP_ISSUES_PER_PHONE_PER_DAY = 5
OTP_ISSUES_PER_IP_PER_DAY = 20
OTP_ISSUES_PER_DEVICE_PER_DAY = 20

# --- verification -------------------------------------------------------------
OTP_VERIFIES_PER_IP_PER_DAY = 50

# --- abuse telemetry ----------------------------------------------------------
# Distinct phones requesting OTPs from one IP in 24h before the audit log fires.
SUSPICIOUS_PHONES_PER_IP = 5

# --- otp_proof ----------------------------------------------------------------
# Verify hands back a single-use proof token (consumed by D08/D09 login), not a
# session. Short-lived: long enough to finish the login redirect dance only.
OTP_PROOF_TTL_SECONDS = 600

DAY_SECONDS = 86400
