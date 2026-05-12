"""Fetch weekly report source files from Lark/Feishu via lark-cli."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

from jobs.weekly_report_config import SourceConfig


class RunnerResult(Protocol):
    returncode: int
    stdout: str
    stderr: str


CliRunner = Callable[[list[str]], RunnerResult]


class SourceFetchError(Exception):
    def __init__(self, error_type: str, message: str):
        super().__init__(message)
        self.error_type = error_type
        self.message = message


def fetch_weekly_sources(
    sources: list[SourceConfig],
    raw_dir: str | Path,
    runner: CliRunner | None = None,
) -> list[dict[str, object]]:
    """Export configured weekly sources to ``raw_dir`` and return manifest items."""
    target_dir = Path(raw_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    run_cli = runner or _run_cli

    manifest: list[dict[str, object]] = []
    for source in sources:
        if not source.enabled:
            manifest.append(_base_manifest(source) | {"status": "skipped", "message": "source disabled"})
            continue

        try:
            resolved_obj_type, resolved_obj_token = _resolve_source(source, run_cli)
            if resolved_obj_type != "sheet":
                raise SourceFetchError(
                    "unsupported_source_type",
                    f"Resolved object type {resolved_obj_type!r} is not supported for weekly detail data",
                )

            output_path = target_dir / f"{source.id}.csv"
            _export_sheet(source, resolved_obj_token, output_path, run_cli)
            manifest.append(
                _base_manifest(source)
                | {
                    "status": "success",
                    "resolved_obj_type": resolved_obj_type,
                    "resolved_obj_token": resolved_obj_token,
                    "export_format": "csv",
                    "local_path": output_path.as_posix(),
                    "row_count": _count_rows(output_path),
                    "file_sha256": _sha256(output_path),
                }
            )
        except SourceFetchError as exc:
            manifest.append(
                _base_manifest(source)
                | {
                    "status": "failed",
                    "error_type": exc.error_type,
                    "message": exc.message,
                }
            )
        except Exception as exc:
            manifest.append(
                _base_manifest(source)
                | {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )

    return manifest


def _resolve_source(source: SourceConfig, runner: CliRunner) -> tuple[str, str]:
    if source.url_type == "sheet":
        return "sheet", source.token

    if source.url_type != "wiki":
        raise SourceFetchError("unsupported_url_type", f"Unsupported source URL type: {source.url_type}")

    args = [
        "npx.cmd",
        "@larksuite/cli",
        "wiki",
        "spaces",
        "get_node",
        "--as",
        "user",
        "--params",
        json.dumps({"token": source.token}, ensure_ascii=False),
        "--format",
        "json",
    ]
    completed = runner(args)
    if completed.returncode != 0:
        raise SourceFetchError("lark_cli_failed", _error_message(completed))

    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise SourceFetchError("invalid_lark_json", f"wiki get_node returned invalid JSON: {exc}") from exc

    node = (payload.get("data") or {}).get("node") or payload.get("node") or {}
    obj_type = node.get("obj_type") or node.get("objType")
    obj_token = node.get("obj_token") or node.get("objToken")
    if not obj_type or not obj_token:
        raise SourceFetchError("invalid_wiki_node", "wiki get_node response did not include obj_type and obj_token")

    return str(obj_type), str(obj_token)


def _export_sheet(source: SourceConfig, spreadsheet_token: str, output_path: Path, runner: CliRunner) -> None:
    args = [
        "npx.cmd",
        "@larksuite/cli",
        "sheets",
        "+export",
        "--as",
        "user",
        "--spreadsheet-token",
        spreadsheet_token,
        "--sheet-id",
        source.sheet_id,
        "--file-extension",
        "csv",
        "--output-path",
        str(output_path),
    ]
    completed = runner(args)
    if completed.returncode != 0:
        raise SourceFetchError("lark_cli_failed", _error_message(completed))
    if not output_path.exists():
        raise SourceFetchError("export_missing_file", f"lark-cli did not create export file: {output_path}")


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)


def _base_manifest(source: SourceConfig) -> dict[str, object]:
    return {
        "source_id": source.id,
        "source_type": source.source_type,
        "original_url": source.url,
        "source_url_type": source.url_type,
        "source_token": source.token,
        "sheet_id": source.sheet_id,
        "department": source.department,
        "site": source.site,
        "source_role": source.source_role,
        "parser": source.parser,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def _error_message(completed: RunnerResult) -> str:
    return (completed.stderr or completed.stdout or f"lark-cli exited with {completed.returncode}").strip()


def _count_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return sum(1 for _ in handle)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
