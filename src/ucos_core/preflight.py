"""Container preflight. Production images exit non-zero if required dependencies fail."""

import sys

from ucos_core.dependencies import production_environment, required_dependencies_ready


def main() -> int:
    if not production_environment():
        return 0
    ready, components = required_dependencies_ready()
    if ready:
        return 0
    unavailable = ", ".join(name for name, ok in components.items() if not ok)
    print(f"production preflight failed; unavailable dependencies: {unavailable}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
