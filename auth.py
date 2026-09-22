"""Single-user authentication for the local Wakeboard server."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
import threading
import time
from pathlib import Path


SESSION_SECONDS = 12 * 60 * 60
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 3


class AuthError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class Authentication:
    def __init__(self, path: Path):
        self.path = path
        self.setup_code = secrets.token_urlsafe(24)
        self.sessions: dict[str, float] = {}
        self.failures: dict[str, list[float]] = {}
        self.lock = threading.Lock()

    def configured(self) -> bool:
        return self.path.exists()

    def _hash(self, password: str, salt: bytes) -> bytes:
        return hashlib.scrypt(
            password.encode("utf-8"), salt=salt,
            n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, maxmem=64 * 1024 * 1024,
        )

    def _read(self) -> tuple[bytes, bytes]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if value.get("algorithm") != "scrypt-v1":
                raise ValueError("unknown algorithm")
            salt, expected = bytes.fromhex(value["salt"]), bytes.fromhex(value["hash"])
            if len(salt) != 16 or len(expected) != 64:
                raise ValueError("invalid hash")
            return salt, expected
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise AuthError("Nie udało się odczytać danych logowania.", 500) from exc

    def _check_limit(self, source: str) -> None:
        now = time.monotonic()
        recent = [attempt for attempt in self.failures.get(source, []) if now - attempt < 60]
        self.failures[source] = recent
        if len(recent) >= 10:
            raise AuthError("Zbyt wiele prób. Spróbuj ponownie za minutę.", 429)

    def _failed(self, source: str) -> None:
        self.failures.setdefault(source, []).append(time.monotonic())

    def _session(self) -> str:
        now = time.monotonic()
        self.sessions = {key: expiry for key, expiry in self.sessions.items() if expiry > now}
        if len(self.sessions) >= 64:
            self.sessions.pop(min(self.sessions, key=self.sessions.get))
        token = secrets.token_urlsafe(32)
        self.sessions[token] = now + SESSION_SECONDS
        return token

    def setup(self, code: str, password: str, source: str) -> str:
        with self.lock:
            if self.configured():
                raise AuthError("Konto admin jest już skonfigurowane.", 409)
            self._check_limit(source)
            if not isinstance(code, str) or not isinstance(password, str):
                raise AuthError("Podaj kod konfiguracji i hasło.")
            if not hmac.compare_digest(code, self.setup_code):
                self._failed(source)
                raise AuthError("Nieprawidłowy kod konfiguracji.", 403)
            if not 12 <= len(password) <= 128:
                raise AuthError("Hasło musi mieć od 12 do 128 znaków.")
            salt = secrets.token_bytes(16)
            digest = self._hash(password, salt)
            temporary = None
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                descriptor, temporary = tempfile.mkstemp(prefix=".auth-", dir=self.path.parent)
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    json.dump({"algorithm": "scrypt-v1", "salt": salt.hex(), "hash": digest.hex()}, stream)
                    stream.write("\n")
                os.replace(temporary, self.path)
            except OSError as exc:
                raise AuthError("Nie udało się zapisać danych logowania w katalogu data.", 500) from exc
            finally:
                if temporary is not None:
                    try:
                        Path(temporary).unlink(missing_ok=True)
                    except OSError:
                        pass
            self.setup_code = ""
            self.failures.pop(source, None)
            self.sessions.clear()
            return self._session()

    def login(self, username: str, password: str, source: str) -> str:
        with self.lock:
            if not self.configured():
                raise AuthError("Najpierw skonfiguruj konto admin.", 409)
            self._check_limit(source)
            if not isinstance(password, str) or len(password) > 128:
                raise AuthError("Nieprawidłowe dane logowania.", 401)
            salt, expected = self._read()
            actual = self._hash(password, salt)
            if username != "admin" or not hmac.compare_digest(actual, expected):
                self._failed(source)
                raise AuthError("Nieprawidłowe dane logowania.", 401)
            self.failures.pop(source, None)
            return self._session()

    def valid(self, token: str) -> bool:
        if not token or not self.configured():
            return False
        with self.lock:
            expires = self.sessions.get(token)
            if expires is None:
                return False
            if expires <= time.monotonic():
                self.sessions.pop(token, None)
                return False
            return True

    def logout(self, token: str) -> None:
        with self.lock:
            self.sessions.pop(token, None)
