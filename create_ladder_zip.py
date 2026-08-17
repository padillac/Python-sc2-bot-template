import importlib
import importlib.metadata
import os
import re
import shutil
import zipfile


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# ========================================
# BOT CONFIGURATION (edit per-bot)
# ========================================
# Framework conventions assumed:
#   - The bot class exposes NAME and VERSION class attributes
#   - The class name inside BOT_MODULE matches the module filename

BOT_PACKAGE = "bot"                  # package directory containing the main bot module
BOT_MODULE = "MyBot"                 # module filename (without .py); also the class name inside it
ENTRY_POINT = "run.py"               # script the ladder invokes
EXTRA_INCLUDES = []                  # extra dirs/files to bundle from the repo (sc2/ is sourced from site-packages, see DISTRIBUTIONS_TO_BUNDLE)
# Pip-installed distributions whose top-level packages should be bundled into the zip.
# Each distribution is version-checked against its `==` pin in requirements.txt, then every top-level
# package it declares (via top_level.txt) is copied from site-packages into the zip root.
DISTRIBUTIONS_TO_BUNDLE = ["burnysc2"]

# ========================================
# LADDER OPTIMIZATION CONFIGURATION
# ========================================

# Desired log level for ladder deployment
# Options: TRACE, DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL
# Lower levels = more verbose logs = worse performance
# Higher levels = faster step time on the ladder
LADDER_LOG_LEVEL = "INFO"

PUBLISH_FOLDER = "publish"

# ========================================

# Dynamically generate directory paths/zip file name
_bot_module = importlib.import_module(f"{BOT_PACKAGE}.{BOT_MODULE}")
bot = getattr(_bot_module, BOT_MODULE)

ZIP_ARCHIVE_NAME = f"{bot.NAME}-{bot.VERSION}.zip"

FILES_AND_DIRECTORIES_TO_ZIP = [BOT_PACKAGE, ENTRY_POINT, *EXTRA_INCLUDES]

REQUIREMENTS_FILE = "requirements.txt"

# Directories to skip entirely during os.walk (never descend into these).
# "dev_tools" is an example entry: add any directory here that you want kept out
# of the ladder build (local analysis scripts, test harnesses, notebooks, etc).
EXCLUDED_DIRS = {
    "__pycache__",
    ".git",
    ".github",
    ".vscode",
    ".idea",
    ".pytest_cache",
    "node_modules",
    "venv",
    ".venv",
    "dev_tools",
}

# Exact filenames to exclude
EXCLUDED_FILES = {
    ".DS_Store",
    "Thumbs.db",
    ".gitignore",
    ".gitattributes",
    ".gitmodules",
}

# File extensions to exclude
EXCLUDED_EXTENSIONS = (
    ".pyc",
    ".pyo",
    ".log",
)

# ========================================


def create_staging_directory() -> str:
    staging_dir = os.path.join(ROOT_DIR, ".ladder_zip_staging")
    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir)
    os.makedirs(staging_dir)
    print(f"Created staging directory: {staging_dir}")
    return staging_dir


_REQUIREMENT_PIN_PATTERN = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*==\s*([^\s;#]+)")


def _parse_pinned_versions(requirements_path: str) -> dict[str, str]:
    """Parse `name==version` pins from requirements.txt. Lines without a == pin are ignored."""
    pins: dict[str, str] = {}
    with open(requirements_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            match = _REQUIREMENT_PIN_PATTERN.match(stripped)
            if match:
                pins[match.group(1).lower()] = match.group(2)
    return pins


def verify_pinned_distributions():
    """Fail loudly if an installed distribution version doesn't match its `==` pin in requirements.txt."""
    requirements_path = os.path.join(ROOT_DIR, REQUIREMENTS_FILE)
    if not os.path.isfile(requirements_path):
        raise FileNotFoundError(f"{REQUIREMENTS_FILE} not found at {requirements_path}")

    pins = _parse_pinned_versions(requirements_path)
    for distribution_name in DISTRIBUTIONS_TO_BUNDLE:
        key = distribution_name.lower()
        if key not in pins:
            raise ValueError(
                f"'{distribution_name}' is in DISTRIBUTIONS_TO_BUNDLE but has no `==` pin in {REQUIREMENTS_FILE}"
            )
        try:
            installed = importlib.metadata.version(distribution_name)
        except importlib.metadata.PackageNotFoundError:
            raise RuntimeError(
                f"'{distribution_name}' is pinned to {pins[key]} in {REQUIREMENTS_FILE} but is not installed. "
                f"Run: pip install -r {REQUIREMENTS_FILE}"
            )
        if installed != pins[key]:
            raise RuntimeError(
                f"'{distribution_name}' version mismatch: {REQUIREMENTS_FILE} pins {pins[key]}, "
                f"but installed version is {installed}. Run: pip install -r {REQUIREMENTS_FILE}"
            )
        print(f"  {distribution_name} {installed} matches pin")


def _top_level_packages(dist: importlib.metadata.Distribution) -> list[str]:
    """Return top-level package names declared by an installed distribution, falling back to the
    distribution name if `top_level.txt` is absent."""
    top_level = dist.read_text("top_level.txt")
    if top_level:
        return [name for name in (line.strip() for line in top_level.splitlines()) if name]
    return [dist.metadata["Name"]]


def copy_distributions_to_staging(staging_dir: str):
    """Copy each configured distribution's top-level packages from site-packages into the zip staging area.

    Uses `Distribution.locate_file` (not `find_spec`) so resolution is anchored to the installed
    distribution, ignoring any same-named directory that might shadow site-packages on sys.path.
    """
    if not DISTRIBUTIONS_TO_BUNDLE:
        return
    print(f"{os.linesep}Copying pip-installed packages from site-packages...")
    for distribution_name in DISTRIBUTIONS_TO_BUNDLE:
        dist = importlib.metadata.distribution(distribution_name)
        for package_name in _top_level_packages(dist):
            src = dist.locate_file(package_name)
            if not src.is_dir():
                raise RuntimeError(
                    f"Top-level package '{package_name}' from '{distribution_name}' "
                    f"is not a directory at {src} — single-file modules are not supported"
                )
            dst = os.path.join(staging_dir, package_name)
            print(f"  Copying {package_name}/ from {src.parent}")
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))


def copy_to_staging(staging_dir: str):
    print(f"{os.linesep}Copying files to staging directory...")
    for item in FILES_AND_DIRECTORIES_TO_ZIP:
        src = os.path.join(ROOT_DIR, item)

        if not os.path.exists(src):
            raise ValueError(f"'{item}' does not exist in {ROOT_DIR}")

        dst = os.path.join(staging_dir, item)

        if os.path.isdir(src):
            print(f"  Copying directory: {item}")
            shutil.copytree(src, dst)
        else:
            print(f"  Copying file: {item}")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)


_LOG_LEVEL_PATTERN = re.compile(r'logger\.add\(sys\.stdout, level="(\w+)"')


def optimize_bot_code(staging_dir: str):
    """Rewrite the staged bot module's log level to LADDER_LOG_LEVEL.

    Only the staged copy is modified — your working tree is untouched. This requires
    the bot module to contain a literal `logger.add(sys.stdout, level="...")` call.
    """
    print(f"{os.linesep}Optimizing bot code for ladder performance...")
    bot_filename = f"{BOT_MODULE}.py"
    bot_file = os.path.join(staging_dir, BOT_PACKAGE, bot_filename)

    if not os.path.exists(bot_file):
        raise FileNotFoundError(
            f"{bot_filename} not found at {bot_file} — cannot optimize for ladder deployment"
        )

    with open(bot_file, 'r', encoding='utf-8') as f:
        content = f.read()

    match = _LOG_LEVEL_PATTERN.search(content)
    if not match:
        raise ValueError(
            f"Could not find logger.add(sys.stdout, level=\"...\") in {bot_filename} "
            "— log level optimization failed"
        )

    current_level = match.group(1)
    if current_level == LADDER_LOG_LEVEL:
        print(f"  Log level already {LADDER_LOG_LEVEL} (no changes needed)")
        return

    content = content[:match.start(1)] + LADDER_LOG_LEVEL + content[match.end(1):]

    with open(bot_file, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"  Log level: {current_level} -> {LADDER_LOG_LEVEL}")


def should_exclude_file(filename: str) -> bool:
    if filename in EXCLUDED_FILES:
        return True
    if filename.endswith(EXCLUDED_EXTENSIONS):
        return True
    return False


def zipdir(path: str, ziph: zipfile.ZipFile):
    excluded_count = 0
    included_count = 0

    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]

        for file in files:
            if should_exclude_file(file):
                excluded_count += 1
                continue

            filepath = os.path.join(root, file)
            arcname = os.path.relpath(filepath, path)
            ziph.write(filepath, arcname)
            included_count += 1

    print(f"  Included {included_count} files")
    if excluded_count > 0:
        print(f"  Excluded {excluded_count} unnecessary files")


def create_ladder_zip():
    os.chdir(ROOT_DIR)

    print(f"Creating optimized ladder zip for {bot.NAME} v{bot.VERSION}...")
    print("=" * 60)

    print(f"{os.linesep}Verifying pinned distribution versions...")
    verify_pinned_distributions()

    staging_dir = create_staging_directory()

    try:
        copy_to_staging(staging_dir)

        copy_distributions_to_staging(staging_dir)

        optimize_bot_code(staging_dir)

        output_path = os.path.join(PUBLISH_FOLDER, ZIP_ARCHIVE_NAME)
        if os.path.isfile(output_path):
            print(f"{os.linesep}Deleting old {output_path}")
            os.remove(output_path)

        print(f"{os.linesep}Creating zip archive: {ZIP_ARCHIVE_NAME}")
        with zipfile.ZipFile(ZIP_ARCHIVE_NAME, "w", zipfile.ZIP_DEFLATED) as zipf:
            zipdir(staging_dir, zipf)

        if not os.path.exists(PUBLISH_FOLDER):
            os.mkdir(PUBLISH_FOLDER)
        shutil.move(ZIP_ARCHIVE_NAME, output_path)

        print("=" * 60)
        print(f"Successfully created optimized ladder package:")
        print(f"  {output_path}")
        print(f"  Ready for ladder deployment!")

    finally:
        if os.path.exists(staging_dir):
            shutil.rmtree(staging_dir)
            print(f"{os.linesep}Cleaned up staging directory")


def main():
    create_ladder_zip()


if __name__ == "__main__":
    main()
