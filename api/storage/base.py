from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class StorageError(RuntimeError): pass
class NotFound(StorageError): pass
class Unavailable(StorageError): pass
class InvalidData(StorageError): pass
class Conflict(StorageError): pass
class StorageConfigurationError(StorageError): pass


@dataclass(frozen=True)
class SessionData:
    metadata: dict[str, Any]
    markdown: str


class Storage(ABC):
    @abstractmethod
    def load_profile(self, user_id: str) -> dict: ...
    @abstractmethod
    def save_profile(self, user_id: str, profile: dict) -> None: ...
    @abstractmethod
    def save_profile_history(self, user_id: str, session_id: str, profile: dict, stage: str) -> None: ...
    @abstractmethod
    def backup_profile_before_migration(self, user_id: str) -> None: ...
    @abstractmethod
    def create_session(self, session_id: str, metadata: dict, markdown: str) -> None: ...
    @abstractmethod
    def load_session(self, session_id: str) -> SessionData: ...
    @abstractmethod
    def update_session(self, session_id: str, metadata: dict, markdown: str) -> None: ...
