import argparse
import importlib
import sys
from pathlib import Path

from fastapi import FastAPI

ROOT = Path(__file__).resolve().parents[1]
ROUTES_FILE = ROOT / "contract" / "routes.txt"
API_PREFIX = "/api/v1"
HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete"})


def load_contract(path: Path) -> tuple[set[str], list[str]]:
    routes: set[str] = set()
    problems: list[str] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        method, _, route = line.partition(" ")
        entry = f"{method.upper()} {route.strip()}"
        if method.lower() not in HTTP_METHODS or not route.strip().startswith(f"{API_PREFIX}/"):
            problems.append(f"line {number}: malformed entry {line!r}")
        elif entry in routes:
            problems.append(f"line {number}: duplicate entry {entry}")
        routes.add(entry)
    return routes, problems


def load_app_routes(app: FastAPI) -> set[str]:
    routes: set[str] = set()
    for path, operations in app.openapi()["paths"].items():
        if not path.startswith(API_PREFIX):
            continue
        for method in operations:
            if method in HTTP_METHODS:
                routes.add(f"{method.upper()} {path}")
    return routes


def build_app() -> FastAPI:
    sys.path.insert(0, str(ROOT))
    module = importlib.import_module("app.main")
    factory = module.create_app
    app = factory()
    if not isinstance(app, FastAPI):
        raise TypeError("create_app did not return a FastAPI instance")
    return app


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare API routes with contract/routes.txt")
    parser.add_argument("--full", action="store_true", help="also fail on missing routes")
    args = parser.parse_args()

    contract, problems = load_contract(ROUTES_FILE)
    exposed = load_app_routes(build_app())
    extra = sorted(exposed - contract)
    missing = sorted(contract - exposed)

    out = sys.stdout
    if problems:
        out.write("Problems in contract/routes.txt:\n")
        out.writelines(f"  ! {problem}\n" for problem in problems)
    if extra:
        out.write("Routes exposed by the app but not in contract/routes.txt:\n")
        out.writelines(f"  + {route}\n" for route in extra)
    if missing:
        label = "Missing" if args.full else "Not yet implemented"
        out.write(f"{label} contract routes ({len(missing)}):\n")
        if args.full:
            out.writelines(f"  - {route}\n" for route in missing)

    failed = bool(problems) or bool(extra) or (args.full and bool(missing))
    out.write(
        f"Contract check {'FAILED' if failed else 'passed'}: "
        f"{len(exposed)} exposed, {len(contract)} in contract, "
        f"{len(extra)} extra, {len(missing)} missing\n"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
