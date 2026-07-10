from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Workspace:
    """Resolved Patchouli workspace paths.

    All path checks resolve against ``root`` (the Patchouli folder), never the
    process cwd alone, and ``abspath`` refuses to escape it.
    """

    root: Path

    @classmethod
    def from_path(cls, path: Path | str | None = None) -> "Workspace":
        candidate = Path.cwd() if path is None else Path(path)
        root = candidate.resolve()
        if root.is_file():
            root = root.parent
        return cls(root=root)

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def extracted(self) -> Path:
        return self.root / "extracted"

    @property
    def wiki(self) -> Path:
        return self.root / "wiki"

    @property
    def searches(self) -> Path:
        return self.root / "searches"

    def relpath(self, path: Path | str) -> str:
        p = Path(path)
        p = p.resolve() if p.is_absolute() else (self.root / p).resolve()
        return p.relative_to(self.root).as_posix()

    def abspath(self, path: Path | str) -> Path:
        p = Path(path)
        resolved = p.resolve() if p.is_absolute() else (self.root / p).resolve()
        self.assert_inside(resolved)
        return resolved

    def confined(self, base: Path | str, *parts: str) -> Path:
        """Resolve an output beneath one real, non-symlinked workspace directory."""

        base_path = Path(base)
        lexical_base = (
            base_path.absolute() if base_path.is_absolute() else (self.root / base_path).absolute()
        )
        resolved_base = lexical_base.resolve()
        self.assert_inside(resolved_base)
        if resolved_base != lexical_base:
            raise ValueError(f"output root must not be a symlink: {lexical_base}")
        relative = Path(*parts)
        cursor = resolved_base
        for part in relative.parts:
            cursor /= part
            if cursor.is_symlink():
                raise ValueError(f"output path component must not be a symlink: {cursor}")
        resolved = cursor.resolve()
        try:
            resolved.relative_to(resolved_base)
        except ValueError as exc:
            raise ValueError(f"path escapes output root {lexical_base}: {resolved}") from exc
        return resolved

    def assert_inside(self, path: Path | str) -> None:
        p = Path(path).resolve()
        try:
            p.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"path escapes workspace: {path}") from exc
