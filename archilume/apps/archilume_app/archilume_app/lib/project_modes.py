"""Project mode registry — single source of truth for the two workflow modes.

Consumed by both the Create New Project modal and the Project Settings modal so
field labels, accept filters, validators, and canonical destinations live in
exactly one place.

Modes
-----
* ``sunlight``   — Sunlight workflow. Accepts geometry (for simulation) and/or
                   pre-rendered HDR results for markup.
* ``daylight``   — Daylight workflow (IESVE). Accepts octree+rdp (for
                   simulation) and/or pre-rendered ``.pic`` results for markup.

Every field is optional at create time — only the project name and mode are
required. Users drop in whatever inputs they have; the UI adapts at runtime
based on what is actually on disk. Fields can still be added, replaced, or
removed later via the Project Settings modal.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from . import project_validators as V

ValidationResult = Tuple[bool, str]
Validator = Callable[[Path], ValidationResult]


# ---------------------------------------------------------------------------
# FieldSpec
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FieldSpec:
    """Declarative description of one upload slot in the create/settings form.

    Attributes
    ----------
    id:
        Stable identifier used as the key in ``new_project_staged`` /
        ``settings_staged`` dicts and as the rx.upload ``id`` prop.
    label:
        Human-readable field title shown in the modal.
    description:
        Short one-line caption rendered beneath the field label.
    accept:
        ``rx.upload``-style accept filter, e.g. ``{"application/pdf": [".pdf"]}``.
    multiple:
        Whether the drop zone accepts multiple files.
    dest_attr:
        Name of the attribute on :class:`archilume.config.ProjectPaths` whose
        ``Path`` is the canonical destination directory (e.g. ``"plans_dir"``).
    validator:
        Callable ``(Path) -> (ok, error_message)`` for per-file validation.
    required:
        If True, the field must have ≥1 valid file (unless it belongs to a
        ``one_of`` group that is satisfied by another member). Defaults to
        False — the two current modes leave every field optional so users
        can populate a project incrementally.
    one_of:
        Optional group key; within a mode, at least one member of the group
        must be satisfied. Members with the same ``one_of`` key are mutually
        substitutable.
    allowed_extensions:
        Lower-case file extensions (including leading dot) accepted for this
        field. Used by the state layer to reject uploads with the wrong suffix
        before running the content validator.
    extension_validators:
        Optional per-extension validator dispatch. When a multi-extension
        field (e.g. geometry accepting ``.obj`` and ``.mtl``) needs different
        validation per suffix, map ``{".obj": validate_obj, ".mtl": validate_mtl}``
        here. The state layer picks the matching validator by file extension
        and falls back to ``validator`` when no mapping is registered.
    """

    id: str
    label: str
    description: str
    accept: Dict[str, List[str]]
    multiple: bool
    dest_attr: str
    validator: Validator
    allowed_extensions: Tuple[str, ...]
    required: bool = False
    one_of: Optional[str] = None
    extension_validators: Optional[Dict[str, Validator]] = None


# ---------------------------------------------------------------------------
# Concrete FieldSpec instances
# ---------------------------------------------------------------------------

PDF = FieldSpec(
    id="pdf",
    label="PDF floor plan",
    description="Floor plan used for overlay alignment",
    accept={"application/pdf": [".pdf"]},
    multiple=False,
    dest_attr="plans_dir",
    validator=V.validate_pdf,
    allowed_extensions=(".pdf",),
)

_GEOMETRY_EXT_VALIDATORS: Dict[str, Validator] = {
    ".obj": V.validate_obj,
    ".mtl": V.validate_mtl,
}

GEOMETRY_BUILDING = FieldSpec(
    id="geometry_building",
    label="Building geometry (.obj + .mtl)",
    description="The building being analysed — exactly one .obj plus its .mtl (same stem).",
    accept={"application/octet-stream": [".obj", ".mtl"]},
    multiple=True,
    dest_attr="inputs_dir",
    validator=V.validate_obj,
    allowed_extensions=(".obj", ".mtl"),
    required=True,
    extension_validators=_GEOMETRY_EXT_VALIDATORS,
)

GEOMETRY_SITE = FieldSpec(
    id="geometry_site",
    label="Site & near-shading geometry (.obj + .mtl)",
    description="Adjacent buildings, trees, ground plane — exactly one .obj plus its .mtl.",
    accept={"application/octet-stream": [".obj", ".mtl"]},
    multiple=True,
    dest_attr="inputs_dir",
    validator=V.validate_obj,
    allowed_extensions=(".obj", ".mtl"),
    required=False,
    extension_validators=_GEOMETRY_EXT_VALIDATORS,
)

HDR_RESULTS = FieldSpec(
    id="hdr_results",
    label="HDR results",
    description="Pre-rendered archilume sunlight HDRs for markup",
    accept={"application/octet-stream": [".hdr"]},
    multiple=True,
    dest_attr="image_dir",
    validator=V.validate_hdr,
    allowed_extensions=(".hdr",),
)

PIC_RESULTS = FieldSpec(
    id="pic_results",
    label="PIC results",
    description="Pre-rendered IESVE daylight .pic files for markup",
    accept={"application/octet-stream": [".pic", ".hdr"]},
    multiple=True,
    dest_attr="pic_dir",
    validator=V.validate_pic,
    allowed_extensions=(".pic", ".hdr"),
)

OCT = FieldSpec(
    id="oct",
    label="Octree (.oct)",
    description="Externally-supplied IESVE octree for daylight simulation",
    accept={"application/octet-stream": [".oct"]},
    multiple=False,
    dest_attr="octree_dir",
    validator=V.validate_oct,
    allowed_extensions=(".oct",),
)

RDP = FieldSpec(
    id="rdp",
    label="Render params (.rdp)",
    description="Radiance render parameters",
    accept={"text/plain": [".rdp"]},
    multiple=False,
    dest_attr="inputs_dir",
    validator=V.validate_rdp,
    allowed_extensions=(".rdp",),
)

ROOM_DATA_SUNLIGHT = FieldSpec(
    id="room_data",
    label="room_boundaries.csv",
    description="Rooms as CSV — converted to .aoi on upload. Mutually exclusive with .aoi files.",
    accept={"text/csv": [".csv"]},
    multiple=False,
    dest_attr="aoi_inputs_dir",
    validator=V.validate_sunlight_room_csv,
    allowed_extensions=(".csv",),
)

ROOM_DATA_IESVE = FieldSpec(
    id="room_data",
    label="IESVE room data (.xlsx / .csv)",
    description="IESVE room data — xlsx is auto-converted to room_boundaries.csv",
    accept={
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
        "text/csv": [".csv"],
    },
    multiple=False,
    dest_attr="aoi_inputs_dir",
    validator=V.validate_room_data,
    allowed_extensions=(".xlsx", ".csv"),
)

AOI_FILES = FieldSpec(
    id="aoi_files",
    label=".aoi files",
    description="Pre-built AOI files defining rooms. Sunlight: mutually exclusive with room_boundaries.csv.",
    accept={"application/octet-stream": [".aoi"]},
    multiple=True,
    dest_attr="aoi_inputs_dir",
    validator=V.validate_aoi,
    allowed_extensions=(".aoi",),
)


# ---------------------------------------------------------------------------
# Mode table
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModeSpec:
    id: str
    display: str
    summary: str
    fields: Tuple[FieldSpec, ...]


MODES: Dict[str, ModeSpec] = {
    "sunlight": ModeSpec(
        id="sunlight",
        display="Sunlight",
        summary=(
            "Sunlight workflow — supply geometry to simulate, or drop in "
            "pre-rendered HDR results to mark up."
        ),
        fields=(PDF, GEOMETRY_BUILDING, GEOMETRY_SITE, HDR_RESULTS, ROOM_DATA_SUNLIGHT, AOI_FILES),
    ),
    "daylight": ModeSpec(
        id="daylight",
        display="Daylight (IESVE)",
        summary=(
            "Daylight workflow — supply IESVE octree + render params to "
            "simulate, or drop in pre-rendered .pic results to mark up."
        ),
        fields=(PDF, OCT, RDP, PIC_RESULTS, AOI_FILES, ROOM_DATA_IESVE),
    ),
}


MODE_IDS: Tuple[str, ...] = tuple(MODES.keys())
DEFAULT_MODE: str = "sunlight"


def get_mode(mode_id: str) -> ModeSpec:
    """Return the :class:`ModeSpec` for ``mode_id`` or raise KeyError."""
    return MODES[mode_id]


def field_by_id(mode_id: str, field_id: str) -> Optional[FieldSpec]:
    """Find a field by id within a mode. Returns None if absent."""
    mode = MODES.get(mode_id)
    if mode is None:
        return None
    for f in mode.fields:
        if f.id == field_id:
            return f
    return None


# ---------------------------------------------------------------------------
# Mode-level satisfaction check
# ---------------------------------------------------------------------------

def mode_required_fields(mode_id: str) -> List[FieldSpec]:
    """Fields that must each be satisfied directly (no one_of grouping)."""
    mode = MODES[mode_id]
    return [f for f in mode.fields if f.required and f.one_of is None]


def mode_one_of_groups(mode_id: str) -> Dict[str, List[FieldSpec]]:
    """Map ``one_of`` group key -> list of member fields."""
    mode = MODES[mode_id]
    groups: Dict[str, List[FieldSpec]] = {}
    for f in mode.fields:
        if f.one_of is None:
            continue
        groups.setdefault(f.one_of, []).append(f)
    return groups


def missing_required(
    mode_id: str,
    staged: Dict[str, List[dict]],
) -> List[str]:
    """Return labels of required fields that have no valid staged file.

    ``staged`` maps ``field_id`` -> list of entries with at least ``{"ok": bool}``.
    A field is "satisfied" if it has ≥1 entry where ``ok`` is True.
    For ``one_of`` groups, the group is satisfied if ANY member field is.
    """

    def field_ok(field_id: str) -> bool:
        entries = staged.get(field_id) or []
        return any(e.get("ok") for e in entries)

    missing: List[str] = []
    for f in mode_required_fields(mode_id):
        if not field_ok(f.id):
            missing.append(f.label)

    for group_key, members in mode_one_of_groups(mode_id).items():
        if not any(field_ok(m.id) for m in members):
            labels = " or ".join(m.label for m in members)
            missing.append(labels)

    return missing


def invalid_combinations(
    mode_id: str,
    staged: Dict[str, List[dict]],
) -> List[str]:
    """Return human-readable errors for mutually-exclusive field combinations.

    Sunlight mode:

    * ``room_data`` (``room_boundaries.csv``) and ``aoi_files`` are each
      individually valid but must not be supplied together — the CSV is
      converted to ``.aoi`` files at project creation and would race with any
      user-supplied ``.aoi`` files.
    * Each geometry slot (``geometry_building``, ``geometry_site``) must
      contain exactly one ``.obj`` and exactly one ``.mtl`` whose stems match.
      Downstream :class:`archilume.core.objs2octree.Objs2Octree` resolves MTL
      paths via ``obj_path.with_suffix('.mtl')`` — a stem mismatch or missing
      MTL causes every material to default to grey plastic.
    """

    def field_ok(field_id: str) -> bool:
        entries = staged.get(field_id) or []
        return any(e.get("ok") for e in entries)

    errors: List[str] = []
    if mode_id == "sunlight":
        if field_ok("room_data") and field_ok("aoi_files"):
            errors.append(
                "Provide either room_boundaries.csv OR .aoi files, not both."
            )
        for slot_id, slot_label in (
            ("geometry_building", "Building geometry"),
            ("geometry_site", "Site geometry"),
        ):
            errors.extend(_geometry_slot_errors(staged, slot_id, slot_label))
    return errors


def _geometry_slot_errors(
    staged: Dict[str, List[dict]],
    slot_id: str,
    slot_label: str,
) -> List[str]:
    """Validate one geometry slot's staged contents (see ``invalid_combinations``).

    Only valid (``ok=True``) entries count — rows flagged by the per-file
    validator are reported separately on the row itself. Returns an empty
    list when the slot is empty (building is marked required elsewhere via
    ``missing_required``).
    """
    entries = [e for e in (staged.get(slot_id) or []) if e.get("ok")]
    if not entries:
        return []

    objs = [e for e in entries if Path(e.get("name", "")).suffix.lower() == ".obj"]
    mtls = [e for e in entries if Path(e.get("name", "")).suffix.lower() == ".mtl"]

    errors: List[str] = []
    if len(objs) > 1:
        errors.append(
            f"{slot_label} must contain exactly one .obj — "
            f"got {len(objs)}. Remove extras."
        )
    if len(mtls) > 1:
        errors.append(
            f"{slot_label} must contain exactly one .mtl — "
            f"got {len(mtls)}. Remove extras."
        )
    if len(objs) == 1 and len(mtls) == 0:
        obj_name = objs[0].get("name", "")
        stem = Path(obj_name).stem
        errors.append(
            f"{slot_label} is missing '{stem}.mtl'. "
            f"Upload the MTL sibling of '{obj_name}'."
        )
    if len(objs) == 0 and len(mtls) == 1:
        errors.append(
            f"{slot_label} has an .mtl without a matching .obj. "
            f"Upload the OBJ, or remove the MTL."
        )
    if len(objs) == 1 and len(mtls) == 1:
        obj_stem = Path(objs[0].get("name", "")).stem
        mtl_stem = Path(mtls[0].get("name", "")).stem
        if obj_stem != mtl_stem:
            errors.append(
                f"{slot_label}: '{objs[0].get('name')}' and "
                f"'{mtls[0].get('name')}' have different stems. "
                f"Rename the MTL to '{obj_stem}.mtl'."
            )
    return errors
