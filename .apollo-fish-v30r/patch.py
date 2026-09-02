from pathlib import Path
import sys

# CI hot-fix hook. Intentionally empty for the first v3.0 build.
root = Path(sys.argv[1])
assert (root / "app" / "build.gradle.kts").is_file()
