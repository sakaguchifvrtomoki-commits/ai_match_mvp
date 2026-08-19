from pathlib import Path
import app as streamlit_app
from api.storage.local import LocalStorage


def get_storage() -> LocalStorage:
    return LocalStorage(Path(streamlit_app.__file__).parent)


__all__ = ["get_storage", "LocalStorage"]
