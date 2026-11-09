from pathlib import Path
from PySide6.QtCore import QStandardPaths

def data_directory() -> Path:
    directory = Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))
    directory.mkdir(parents=True, exist_ok=True)
    return directory
