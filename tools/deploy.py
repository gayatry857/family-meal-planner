"""Update the live demo on Azure from the files in this folder.

    python tools/deploy.py

Needs the Azure CLI, signed in (`az login`). Pushing to GitHub does NOT update
the live app; this does. Only runtime files are uploaded, never .env or a
database.
"""

import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GROUP, APP = "meal-planner-rg", "family-meal-planner"
FILES = ["requirements.txt", "startup.sh"]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        package = Path(tmp) / "deploy.zip"
        with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as z:
            for name in FILES:
                z.write(ROOT / name, name)
            for path in sorted((ROOT / "app").rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts \
                        and not path.name.startswith((".env", "meals.db")) \
                        and path.suffix != ".db":
                    z.write(path, path.relative_to(ROOT).as_posix())
        subprocess.run(
            [shutil.which("az"), "webapp", "deploy", "-g", GROUP, "-n", APP,
             "--src-path", str(package), "--type", "zip", "--timeout", "600"],
            check=True,
        )


if __name__ == "__main__":
    main()
