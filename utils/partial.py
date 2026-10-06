from pathlib import Path

PARTIAL_EXTENSIONS = {
    ".crdownload", ".part", ".partial", ".tmp", ".download", ".opdownload", ".!ut",
}


def _is_partial(path: Path) -> bool:
    return path.suffix.lower() in PARTIAL_EXTENSIONS or path.name.startswith("~$")