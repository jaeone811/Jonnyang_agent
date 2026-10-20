"""앱/폴더 별칭. config/aliases.yaml(사람이 편집) + SQLite(명령으로 등록, 우선)."""

from __future__ import annotations

from jonnyang.core.storage import Storage, iso


class AliasBook:
    def __init__(self, storage: Storage, config: dict, clock):
        self.storage = storage
        self.clock = clock
        self.base: dict[str, tuple[str, str]] = {}
        for name, target in (config.get("apps") or {}).items():
            self.base[str(name)] = ("app", str(target))
        for name, target in (config.get("folders") or {}).items():
            self.base[str(name)] = ("folder", str(target))

    def _user(self) -> dict[str, tuple[str, str]]:
        return {r["name"]: (r["kind"], r["target"]) for r in self.storage.query("SELECT * FROM aliases")}

    def all(self) -> dict[str, tuple[str, str]]:
        return {**self.base, **self._user()}

    def names(self) -> list[str]:
        return sorted(self.all())

    def get(self, name: str) -> tuple[str, str] | None:
        return self.all().get(name)

    def resolve(self, name: str) -> tuple[str, str]:
        return self.all()[name]

    def set(self, name: str, kind: str, target: str) -> None:
        self.storage.execute(
            "INSERT INTO aliases(name, kind, target, created) VALUES(?, ?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET kind = excluded.kind, target = excluded.target",
            (name, kind, target, iso(self.clock())))

    def delete(self, name: str) -> None:
        self.storage.execute("DELETE FROM aliases WHERE name = ?", (name,))
