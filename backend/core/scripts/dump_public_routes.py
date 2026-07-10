"""CI gate: every public route must be declared in public_routes.txt.

The threat is a PR quietly adding public=True to an endpoint. create_app()
already collects every SecureRouter public path into app.state.public_routes;
this script prints that registry, or with --check diffs it against the
committed backend/core/public_routes.txt and fails on any drift. Making a
route public therefore requires editing that file in the same PR, where a
reviewer sees it.

Run from backend/core:

    python scripts/dump_public_routes.py          # print live registry
    python scripts/dump_public_routes.py --check  # diff vs public_routes.txt
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import create_app  # noqa: E402

REGISTRY_FILE = Path(__file__).resolve().parent.parent / "public_routes.txt"


def live_routes() -> list[str]:
    return sorted(set(create_app().state.public_routes))


def declared_routes() -> list[str]:
    lines = REGISTRY_FILE.read_text(encoding="utf-8").splitlines()
    return sorted({line.strip() for line in lines if line.strip() and not line.startswith("#")})


def check() -> int:
    live = set(live_routes())
    declared = set(declared_routes())
    undeclared = sorted(live - declared)
    stale = sorted(declared - live)
    for path in undeclared:
        print(f"UNDECLARED public route: {path}", flush=True)  # noqa: T201 - CI gate output
    for path in stale:
        print(f"STALE declaration (no such public route): {path}", flush=True)  # noqa: T201
    if undeclared or stale:
        print(  # noqa: T201
            "\npublic-routes gate FAILED. If this exposure is deliberate, edit "
            "backend/core/public_routes.txt in this PR so the change is visible in review.",
            flush=True,
        )
        return 1
    print(f"public-routes gate OK — {len(live)} declared public route(s)", flush=True)  # noqa: T201
    return 0


def main() -> int:
    if "--check" in sys.argv[1:]:
        return check()
    for path in live_routes():
        print(path, flush=True)  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
