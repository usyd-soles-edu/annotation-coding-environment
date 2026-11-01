"""Loads and matches data from multiple .ace files for agreement computation."""

import hashlib
import sqlite3
from pathlib import Path

from ace.db.schema import ACE_APPLICATION_ID
from ace.services.agreement_types import (
    AgreementDataset,
    CoderInfo,
    MatchedAnnotation,
    MatchedCode,
    MatchedSource,
)


class AgreementLoader:
    """Loads multiple .ace files, validates them, extracts and matches data."""

    def __init__(self):
        self._files: list[dict] = []  # metadata per file
        self._file_data: list[dict] = []  # extracted data per file

    @property
    def file_count(self) -> int:
        return len(self._files)

    def add_file(self, path: Path | str) -> dict:
        """Add an .ace file. Returns metadata dict with coder_names, source_count, etc.

        On error, returns dict with 'error' key.
        """
        path = Path(path)
        warnings: list[str] = []

        # Check WAL file
        wal_path = Path(str(path) + "-wal")
        if wal_path.exists():
            warnings.append(
                f"'{path.name}' may have uncommitted changes. "
                "Close ACE on this file first."
            )

        # Open read-only
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
        except sqlite3.OperationalError as e:
            return {"error": f"Cannot open '{path.name}': {e}"}

        try:
            # Validate application_id
            app_id = conn.execute("PRAGMA application_id").fetchone()[0]
            if app_id != ACE_APPLICATION_ID:
                return {
                    "error": f"'{path.name}' is not a valid ACE project file."
                }

            # Extract metadata
            coders = conn.execute("SELECT id, name FROM coder").fetchall()
            coder_names = [c["name"] for c in coders]

            source_count = conn.execute(
                "SELECT COUNT(*) FROM source"
            ).fetchone()[0]

            annotation_count = conn.execute(
                "SELECT COUNT(*) FROM annotation WHERE deleted_at IS NULL"
            ).fetchone()[0]

            if annotation_count == 0:
                return {
                    "error": f"'{path.name}' has no annotations."
                }

            # Extract full data for matching
            file_data = self._extract_file_data(conn, path)
            self._file_data.append(file_data)

            info = {
                "path": str(path),
                "filename": path.name,
                "coder_names": coder_names,
                "source_count": source_count,
                "annotation_count": annotation_count,
                "warnings": warnings,
                "error": None,
            }
            self._files.append(info)
            return info

        finally:
            conn.close()

    def _extract_file_data(self, conn: sqlite3.Connection, path: Path) -> dict:
        """Extract sources, codes, coders, annotations from a single file."""
        # Project metadata — the project id identifies copies of one project,
        # which must agree on source UUIDs when matching by content.
        project = conn.execute("SELECT id, codebook_hash FROM project").fetchone()
        codebook_hash = project["codebook_hash"] if project else None
        project_id = project["id"] if project else None

        # Sources with content
        sources = conn.execute(
            "SELECT s.id, s.display_id, sc.content_text, sc.content_hash "
            "FROM source s JOIN source_content sc ON s.id = sc.source_id"
        ).fetchall()

        # Codes — group_name/sort_order/deleted_at may not exist in older .ace files
        col_info = conn.execute("PRAGMA table_info(codebook_code)").fetchall()
        col_names = {row["name"] for row in col_info}
        has_group = "group_name" in col_names
        has_sort = "sort_order" in col_names
        has_deleted_at = "deleted_at" in col_names
        has_kind = "kind" in col_names

        code_cols = "id, name"
        if has_group:
            code_cols += ", group_name"
        if has_sort:
            code_cols += ", sort_order"
        where_parts = []
        if has_deleted_at:
            where_parts.append("deleted_at IS NULL")
        if has_kind:
            where_parts.append("kind = 'code'")
        where = " WHERE " + " AND ".join(where_parts) if where_parts else ""
        order = " ORDER BY sort_order" if has_sort else ""
        codes = conn.execute(
            f"SELECT {code_cols} FROM codebook_code{where}{order}"
        ).fetchall()

        # Coders
        coders = conn.execute("SELECT id, name FROM coder").fetchall()

        # Annotations (non-deleted)
        annotations = conn.execute(
            "SELECT a.source_id, a.coder_id, a.code_id, a.start_offset, a.end_offset "
            "FROM annotation a WHERE a.deleted_at IS NULL"
        ).fetchall()

        # Build lookup maps. text_fingerprint is derived from the actual text:
        # stored content_hash values can be stale and must never decide identity.
        source_map = {
            s["id"]: {
                **dict(s),
                "text_fingerprint": hashlib.sha256(s["content_text"].encode("utf-8")).hexdigest(),
            }
            for s in sources
        }
        code_map = {
            c["id"]: {
                "name": c["name"],
                "group_name": c["group_name"] if has_group else None,
                "sort_order": c["sort_order"] if has_sort else i,
            }
            for i, c in enumerate(codes)
        }
        coder_map = {c["id"]: c["name"] for c in coders}

        return {
            "path": str(path),
            "project_id": project_id,
            "codebook_hash": codebook_hash,
            "sources": source_map,
            "codes": code_map,
            "coders": coder_map,
            "annotations": [dict(a) for a in annotations],
        }

    def validate(self) -> dict:
        """Cross-file validation. Returns summary with matched/unmatched counts and warnings."""
        warnings: list[str] = []

        if len(self._file_data) < 2:
            return {
                "valid": False,
                "error": "Add at least one more coder file.",
                "warnings": warnings,
            }

        # Resolve source identities: shared stored IDs first, then unique content.
        matches, match_error = self._match_sources()
        if match_error:
            return {"valid": False, "error": match_error, "warnings": warnings}

        if not matches:
            return {
                "valid": False,
                "error": "These files share no source texts. Are they from the same project?",
                "warnings": warnings,
            }

        total_sources = self._total_source_identities(matches)
        if len(matches) < total_sources:
            warnings.append(
                f"{len(matches)} of {total_sources} sources match across all files. "
                "Agreement can only use matched source texts."
            )

        eligible_keys = self._eligible_match_keys(matches)
        if not eligible_keys:
            return {
                "valid": False,
                "error": (
                    "These files share no source texts that are coded by every coder. "
                    "Agreement cannot be computed."
                ),
                "warnings": warnings,
            }
        if len(eligible_keys) < len(matches):
            warnings.append(
                f"{len(eligible_keys)} of {len(matches)} matched sources "
                "are coded by every coder. Agreement will be computed on those sources only."
            )

        # Match codes by name (or fast-path via codebook_hash)
        codebook_hashes = [fd["codebook_hash"] for fd in self._file_data]
        fast_path = all(h == codebook_hashes[0] and h is not None for h in codebook_hashes)

        if fast_path:
            # All codebooks identical — use names from first file
            common_code_names = {info["name"] for info in self._file_data[0]["codes"].values()}
        else:
            name_sets = [{info["name"] for info in fd["codes"].values()} for fd in self._file_data]
            common_code_names = name_sets[0].intersection(*name_sets[1:])

            all_code_names = set()
            for ns in name_sets:
                all_code_names |= ns

            if not common_code_names:
                return {
                    "valid": False,
                    "error": "These files share no codes. Agreement cannot be computed.",
                    "warnings": warnings,
                }

            unmatched = len(all_code_names) - len(common_code_names)
            if unmatched > 0:
                warnings.append(
                    f"{len(common_code_names)} of {len(all_code_names)} codes match. "
                    "Unmatched codes will be excluded."
                )

        # Identify coders
        coder_labels = self._resolve_coder_labels()

        return {
            "valid": True,
            "error": None,
            "matched_sources": len(eligible_keys),
            "matched_codes": len(common_code_names),
            "coders": [c.label for c in coder_labels],
            "n_coders": len(coder_labels),
            "warnings": warnings,
        }

    def _match_sources(self) -> tuple[list[dict], str | None]:
        """Resolve cross-file source identities.

        Returns (matches, error). Each match is one source identity present in
        every file, as a dict with "key", per-file source "ids", "display_id"
        and "content_text". Source IDs shared by every file match first and must
        carry identical content; remaining sources match only on content that is
        unique within every file. Ambiguous duplicates are rejected, never pooled.
        """
        files = self._file_data
        if not files:
            return [], None

        # A shared stored source ID must never silently match conflicting content.
        # Verify the actual text (fingerprint), not the stored content_hash.
        first_seen: dict[str, tuple[str, str, str]] = {}  # id -> (fingerprint, filename, display_id)
        for fd in files:
            filename = Path(fd["path"]).name
            for sid, src in fd["sources"].items():
                seen = first_seen.get(sid)
                if seen and seen[0] != src["text_fingerprint"]:
                    return [], (
                        f"Source '{seen[2]}' (ID {sid[:8]}) has different text in "
                        f"'{seen[1]}' and '{filename}'. Compare unmodified copies of "
                        "the same project, or re-import the sources."
                    )
                first_seen[sid] = (src["text_fingerprint"], filename, src["display_id"])

        common_ids = set(files[0]["sources"])
        for fd in files[1:]:
            common_ids &= set(fd["sources"])

        matches: list[dict] = []
        for sid in sorted(common_ids):
            first = files[0]["sources"][sid]
            matches.append({
                "key": f"id:{sid}",
                "ids": [sid] * len(files),
                "display_id": first["display_id"],
                "content_text": first["content_text"],
            })

        # Unknown provenance cannot establish independent imports; keep UUID matches only.
        for fd in files:
            project_id = fd.get("project_id")
            if not isinstance(project_id, str) or not project_id.strip():
                return matches, None

        # Content fallback for sources without a shared ID: one per file, or reject.
        leftover: dict[tuple[int, str], list[str]] = {}
        for i, fd in enumerate(files):
            for sid, src in fd["sources"].items():
                if sid not in common_ids:
                    leftover.setdefault((i, src["text_fingerprint"]), []).append(sid)

        for fingerprint in sorted({h for _, h in leftover}):
            per_file = [leftover.get((i, fingerprint), []) for i in range(len(files))]
            if not all(per_file):
                continue  # not present in every file
            for i, ids in enumerate(per_file):
                if len(ids) > 1:
                    display_id = files[i]["sources"][ids[0]]["display_id"]
                    return [], (
                        f"'{display_id}' shares identical text with another source in "
                        f"'{Path(files[i]['path']).name}' and the files share no source "
                        "ID for them, so they cannot be matched reliably. Compare coder "
                        "copies of the same original project, without altering the "
                        "original response text."
                    )
            # Files copied from one project (same project id) must agree on the
            # source UUID for this text: independently re-imported sources in a
            # copy are different respondents, not one identity bridged by
            # content — even when an independent file holds the same text.
            ids_by_project: dict[str, set[str]] = {}
            for i, fd in enumerate(files):
                pid = fd.get("project_id")
                if pid is not None:
                    ids_by_project.setdefault(pid, set()).update(per_file[i])
            if any(len(uuids) > 1 for uuids in ids_by_project.values()):
                continue

            first = files[0]["sources"][per_file[0][0]]
            matches.append({
                "key": f"content:{fingerprint}",
                "ids": [ids[0] for ids in per_file],
                "display_id": first["display_id"],
                "content_text": first["content_text"],
            })

        return matches, None

    def _total_source_identities(self, matches: list[dict]) -> int:
        """Total source identities: matches count once, unmatched by distinct ID.

        Shared by validate() warnings and the results context bar so both
        report identities, never file entries or text hashes.
        """
        matched_ids = {sid for m in matches for sid in m["ids"]}
        unmatched_ids = {
            sid
            for fd in self._file_data
            for sid in fd["sources"]
            if sid not in matched_ids
        }
        return len(matches) + len(unmatched_ids)

    @staticmethod
    def _annotators_by_source(fd: dict) -> dict[str, set[str]]:
        annotators: dict[str, set[str]] = {}
        for ann in fd["annotations"]:
            annotators.setdefault(ann["source_id"], set()).add(ann["coder_id"])
        return annotators

    def _eligible_match_keys(self, matches: list[dict]) -> set[str]:
        """Matched identities coded by every active coder in every file."""
        per_file = [
            (self._active_coder_ids(fd), self._annotators_by_source(fd))
            for fd in self._file_data
        ]
        return {
            m["key"]
            for m in matches
            if all(
                active <= annotators.get(m["ids"][i], set())
                for i, (active, annotators) in enumerate(per_file)
            )
        }

    @staticmethod
    def _active_coder_ids(fd: dict) -> set[str]:
        known_coder_ids = set(fd["coders"])
        return {
            ann["coder_id"]
            for ann in fd["annotations"]
            if ann["coder_id"] in known_coder_ids
        }

    def _resolve_coder_labels(self) -> list[CoderInfo]:
        """Build unique coder identities from all files."""
        # First pass: collect all (coder_name, file_index, coder_id, path) tuples
        raw: list[tuple[str, int, str, str]] = []
        name_counts: dict[str, int] = {}
        for i, fd in enumerate(self._file_data):
            active_coder_ids = self._active_coder_ids(fd)
            for coder_id, coder_name in fd["coders"].items():
                if coder_id not in active_coder_ids:
                    continue
                raw.append((coder_name, i, coder_id, fd["path"]))
                name_counts[coder_name] = name_counts.get(coder_name, 0) + 1

        # Second pass: disambiguate names that appear more than once or are "default"
        coders: list[CoderInfo] = []
        for coder_name, i, coder_id, path in raw:
            if name_counts[coder_name] > 1 or coder_name == "default":
                label = f"{coder_name} ({Path(path).stem})"
            else:
                label = coder_name
            coders.append(CoderInfo(id=f"{i}_{coder_id}", label=label, source_file=path))

        return coders

    def build_dataset(self) -> AgreementDataset:
        """Build the unified AgreementDataset from all loaded files.

        Call validate() first to ensure data is valid.
        """
        validation = self.validate()
        if not validation["valid"]:
            raise ValueError(validation["error"])

        # Resolve coders
        coders = self._resolve_coder_labels()

        # Matched identities that are present and coded in every file.
        matches, _ = self._match_sources()
        eligible_keys = self._eligible_match_keys(matches)  # once per pass, not per match
        eligible_matches = [m for m in matches if m["key"] in eligible_keys]

        sources = [
            MatchedSource(
                source_key=m["key"],
                display_id=m["display_id"],
                content_text=m["content_text"],
            )
            for m in eligible_matches
        ]
        key_by_file_source_id = [
            {m["ids"][i]: m["key"] for m in eligible_matches}
            for i in range(len(self._file_data))
        ]

        # Match codes
        codebook_hashes = [fd["codebook_hash"] for fd in self._file_data]
        fast_path = all(h == codebook_hashes[0] and h is not None for h in codebook_hashes)

        if fast_path:
            common_code_names = {info["name"] for info in self._file_data[0]["codes"].values()}
        else:
            name_sets = [{info["name"] for info in fd["codes"].values()} for fd in self._file_data]
            common_code_names = name_sets[0].intersection(*name_sets[1:])

        code_meta: dict[str, tuple[str | None, int]] = {}
        for fd in self._file_data:
            for info in fd["codes"].values():
                if info["name"] not in code_meta:
                    code_meta[info["name"]] = (info["group_name"], info["sort_order"])

        codes = sorted(
            [
                MatchedCode(
                    name=n,
                    group_name=code_meta.get(n, (None, 0))[0],
                    sort_order=code_meta.get(n, (None, 0))[1],
                )
                for n in common_code_names
            ],
            key=lambda c: c.sort_order,
        )
        code_name_set = common_code_names

        # Build annotations
        annotations: list[MatchedAnnotation] = []
        for i, fd in enumerate(self._file_data):
            key_by_source_id = key_by_file_source_id[i]
            code_id_to_info = fd["codes"]

            for ann in fd["annotations"]:
                source_key = key_by_source_id.get(ann["source_id"])
                if source_key is None:
                    continue  # source not matched, or not coded in every file
                code_info = code_id_to_info.get(ann["code_id"])
                code_name = code_info["name"] if code_info is not None else None
                if code_name not in code_name_set:
                    continue

                coder_unique_id = f"{i}_{ann['coder_id']}"
                annotations.append(
                    MatchedAnnotation(
                        source_key=source_key,
                        coder_id=coder_unique_id,
                        code_name=code_name,
                        start_offset=ann["start_offset"],
                        end_offset=ann["end_offset"],
                    )
                )

        # Update codes with present_in
        coder_codes: dict[str, set[str]] = {c.name: set() for c in codes}
        for ann in annotations:
            if ann.code_name in coder_codes:
                coder_codes[ann.code_name].add(ann.coder_id)
        for code in codes:
            code.present_in = coder_codes[code.name]

        # Collect all warnings
        all_warnings = list(validation.get("warnings", []))
        for f in self._files:
            all_warnings.extend(f.get("warnings", []))

        return AgreementDataset(
            sources=sources,
            coders=coders,
            codes=codes,
            annotations=annotations,
            warnings=all_warnings,
        )
