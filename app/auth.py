"""A single shared PIN that guards the whole app.

The app is reachable on a public URL and holds the family's health details,
so every request is checked server-side. A signed cookie carries its own
expiry, short enough that leaving the app locks it behind the PIN again.
"""

import base64
import hashlib
import hmac
import logging
import os
import time

logger = logging.getLogger("mealplanner.auth")

COOKIE_NAME = "mealplanner_session"


def _idle_minutes() -> int:
    """How long the app may sit unused before the PIN is asked for again.

    Set SESSION_MINUTES in the environment to change it without a code change
    or a redeploy. Anything unreadable falls back to the default rather than
    crashing the app on startup.
    """
    try:
        minutes = int(os.environ.get("SESSION_MINUTES", "").strip())
    except ValueError:
        minutes = 0
    return minutes if minutes > 0 else 30


# The window slides: every request she makes pushes it back, so she is never
# interrupted while actually using the app. Picking the phone up after a break
# starts at the PIN screen.
IDLE_MINUTES = _idle_minutes()
SESSION_SECONDS = IDLE_MINUTES * 60

# A short PIN is easy to guess by brute force, so slow attackers down.
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60
_attempts: dict[str, list] = {}  # ip -> [fail_count, locked_until]


MIN_PIN_LENGTH = 6

# The handful of PINs an attacker would try first.
_OBVIOUS_PINS = {
    "000000", "111111", "123456", "654321", "121212", "112233", "123123",
    "999999", "696969", "000000", "159753", "147258", "102030", "123321",
}


def configured_pin() -> str:
    return os.environ.get("APP_PIN", "").strip()


def pin_weakness(pin: str) -> str | None:
    """Why this PIN is too easy to guess, or None if it is fine.

    A public URL means anyone can try PINs, so a weak one is a real risk
    rather than a theoretical one.
    """
    if not pin:
        return "No PIN has been set."
    if len(pin) < MIN_PIN_LENGTH:
        return f"The PIN must be at least {MIN_PIN_LENGTH} characters."
    if pin.isdigit():
        if pin in _OBVIOUS_PINS:
            return "That is one of the most commonly guessed PINs."
        if len(set(pin)) == 1:
            return "The PIN cannot be the same digit repeated."
        digits = [int(d) for d in pin]
        steps = {b - a for a, b in zip(digits, digits[1:])}
        if steps <= {1} or steps <= {-1}:
            return "The PIN cannot be a run of consecutive digits."
    return None


def is_configured() -> bool:
    """True only when a PIN is set AND strong enough to be worth having."""
    return pin_weakness(configured_pin()) is None


def _secret() -> bytes:
    """Key used to sign session cookies.

    Derived from the PIN (plus APP_SECRET when set) so it stays the same
    across restarts without extra configuration, and so changing the PIN
    automatically signs everyone out.
    """
    material = configured_pin() + os.environ.get("APP_SECRET", "")
    return hashlib.sha256(("mealplanner-session-v1:" + material).encode()).digest()


def _sign(payload: str) -> str:
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode().rstrip("=")


def make_session_token() -> str:
    """Token carrying its own expiry, signed so it cannot be forged."""
    expires_at = str(int(time.time()) + SESSION_SECONDS)
    return f"{expires_at}.{_sign(expires_at)}"


def token_is_valid(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    expires_at, _, signature = token.partition(".")
    if not hmac.compare_digest(signature, _sign(expires_at)):
        return False
    try:
        return int(expires_at) > time.time()
    except ValueError:
        return False


def check_pin(submitted: str, client_ip: str) -> tuple[bool, str]:
    """Verify the PIN. Returns (ok, message_when_not_ok)."""
    now = time.time()
    fails, locked_until = _attempts.get(client_ip, [0, 0.0])
    if now < locked_until:
        minutes = max(1, int((locked_until - now) / 60))
        return False, f"Too many tries. Please wait {minutes} minutes and try again."

    weakness = pin_weakness(configured_pin())
    if weakness:
        return False, f"This app is not set up correctly. {weakness}"

    # Constant-time so the comparison cannot leak the PIN a digit at a time.
    if hmac.compare_digest(submitted.strip(), configured_pin()):
        _attempts.pop(client_ip, None)
        return True, ""

    fails += 1
    if fails >= MAX_ATTEMPTS:
        _attempts[client_ip] = [0, now + LOCKOUT_SECONDS]
        logger.warning("PIN locked out for %s after %d failed tries", client_ip, fails)
        return False, "Too many tries. Please wait 15 minutes and try again."
    _attempts[client_ip] = [fails, 0.0]
    logger.info("Wrong PIN from %s (try %d of %d)", client_ip, fails, MAX_ATTEMPTS)
    return False, f"That PIN is not right. {MAX_ATTEMPTS - fails} tries left."
