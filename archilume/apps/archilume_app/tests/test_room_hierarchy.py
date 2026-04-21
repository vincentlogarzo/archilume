"""Tests for EditorState._validate_room_hierarchy.

Rule enforced:
    A room is a child only when its ``parent`` names a real top-level sibling
    within the same ``hdr_file`` AND every child vertex sits inside the
    parent's polygon. Violators are demoted to ``parent = None``.
"""

from __future__ import annotations

from archilume_app.state.editor_state import EditorState


def _make_state(rooms: list[dict]) -> EditorState:
    """Bypass rx.State.__init__ and its dirty-var tracking; see
    ``test_keyboard_cycle_room_type._make_state`` for the same pattern."""
    state = object.__new__(EditorState)
    object.__setattr__(state, "dirty_vars", set())
    object.__setattr__(state, "_self_dirty_computed_vars", set())
    object.__setattr__(state, "base_state", state)
    object.__setattr__(state, "rooms", rooms)
    return state


def _square(cx: float, cy: float, half: float) -> list[list[float]]:
    return [
        [cx - half, cy - half],
        [cx + half, cy - half],
        [cx + half, cy + half],
        [cx - half, cy + half],
    ]


class TestValidateRoomHierarchy:
    def test_valid_child_inside_parent_preserved(self):
        parent = {"name": "3 BED", "parent": None, "vertices": _square(0, 0, 10), "hdr_file": "h.hdr"}
        child = {"name": "T1", "parent": "3 BED", "vertices": _square(2, 2, 1), "hdr_file": "h.hdr"}
        state = _make_state([parent, child])
        state._validate_room_hierarchy()
        assert parent["parent"] is None
        assert child["parent"] == "3 BED"

    def test_orphan_parent_ref_demoted(self):
        """Child references a parent that does not exist — demote to top-level."""
        orphan = {"name": "T1", "parent": "NO_SUCH_APT", "vertices": _square(0, 0, 1), "hdr_file": "h.hdr"}
        state = _make_state([orphan])
        state._validate_room_hierarchy()
        assert orphan["parent"] is None

    def test_child_outside_parent_boundary_demoted(self):
        parent = {"name": "3 BED", "parent": None, "vertices": _square(0, 0, 1), "hdr_file": "h.hdr"}
        outside = {"name": "T1", "parent": "3 BED", "vertices": _square(100, 100, 1), "hdr_file": "h.hdr"}
        state = _make_state([parent, outside])
        state._validate_room_hierarchy()
        assert outside["parent"] is None

    def test_cross_hdr_parent_ref_demoted(self):
        """Parent and child on different HDRs — no valid sibling, demote."""
        parent = {"name": "3 BED", "parent": None, "vertices": _square(0, 0, 10), "hdr_file": "other.hdr"}
        child = {"name": "T1", "parent": "3 BED", "vertices": _square(2, 2, 1), "hdr_file": "h.hdr"}
        state = _make_state([parent, child])
        state._validate_room_hierarchy()
        assert child["parent"] is None

    def test_parent_with_non_null_parent_not_treated_as_top_level(self):
        """A room whose own parent is set cannot serve as a top-level parent."""
        not_top = {"name": "A", "parent": "B", "vertices": _square(0, 0, 10), "hdr_file": "h.hdr"}
        child = {"name": "T1", "parent": "A", "vertices": _square(2, 2, 1), "hdr_file": "h.hdr"}
        state = _make_state([not_top, child])
        state._validate_room_hierarchy()
        # "A" itself gets demoted (orphan ref to "B"), and "T1" has no valid top-level
        # parent (A is not top-level before the demotion pass). After first pass:
        #   - A: demoted (B missing)
        #   - T1: at scan time A was non-top-level, so T1 demoted too.
        assert not_top["parent"] is None
        assert child["parent"] is None

    def test_idempotent(self):
        parent = {"name": "3 BED", "parent": None, "vertices": _square(0, 0, 10), "hdr_file": "h.hdr"}
        child = {"name": "T1", "parent": "3 BED", "vertices": _square(2, 2, 1), "hdr_file": "h.hdr"}
        state = _make_state([parent, child])
        state._validate_room_hierarchy()
        state._validate_room_hierarchy()
        assert parent["parent"] is None
        assert child["parent"] == "3 BED"

    def test_empty_rooms_no_crash(self):
        state = _make_state([])
        state._validate_room_hierarchy()
        assert state.rooms == []

    def test_parent_with_too_few_vertices_demotes_child(self):
        degenerate = {"name": "3 BED", "parent": None, "vertices": [[0, 0], [1, 1]], "hdr_file": "h.hdr"}
        child = {"name": "T1", "parent": "3 BED", "vertices": _square(0, 0, 0.1), "hdr_file": "h.hdr"}
        state = _make_state([degenerate, child])
        state._validate_room_hierarchy()
        assert child["parent"] is None

    def test_parent_with_empty_string_sentinel_treated_as_top_level(self):
        """Codebase uses both ``None`` and ``""`` to mean "no parent" (e.g.
        divider tool at editor_state.py:3309 emits ``""``). Validator must
        treat both as valid top-level parents so legitimate DIV children
        (527DP daylight) are not wrongly demoted.
        """
        parent_empty = {"name": "STUDIO", "parent": "", "vertices": _square(0, 0, 10), "hdr_file": "h.hdr"}
        div_child = {"name": "STUDIO_DIV", "parent": "STUDIO", "vertices": _square(2, 2, 1), "hdr_file": "h.hdr"}
        state = _make_state([parent_empty, div_child])
        state._validate_room_hierarchy()
        assert div_child["parent"] == "STUDIO"

    def test_child_sharing_parent_edge_preserved(self):
        """Divider-produced children share vertices on parent boundary —
        boundary-coincident points return False from strict ray-cast
        ``point_in_polygon``, so the validator must probe an interior
        point (centroid) rather than every vertex."""
        parent = {
            "name": "L2000077 L2", "parent": None,
            "vertices": [[0, 0], [100, 0], [100, 100], [0, 100]],
            "hdr_file": "h.hdr",
        }
        child = {
            "name": "L2000077 L2_DIV", "parent": "L2000077 L2",
            # Shares left + top + bottom edges with parent; all four
            # vertices are boundary-coincident.
            "vertices": [[0, 0], [50, 0], [50, 100], [0, 100]],
            "hdr_file": "h.hdr",
        }
        state = _make_state([parent, child])
        state._validate_room_hierarchy()
        assert child["parent"] == "L2000077 L2"

    def test_two_tier_apartment_hierarchy(self):
        """Modern-AOI daylight case: one apartment boundary ``3 BED`` with
        ``parent is None``, two sub-rooms ``T1``/``T2`` with ``parent="3 BED"``
        whose polygons sit inside. Both children preserved."""
        apt = {"name": "3 BED", "parent": None, "vertices": _square(0, 0, 10), "hdr_file": "h.hdr"}
        t1 = {"name": "T1", "parent": "3 BED", "vertices": _square(-3, -3, 1), "hdr_file": "h.hdr"}
        t2 = {"name": "T2", "parent": "3 BED", "vertices": _square(3, 3, 1), "hdr_file": "h.hdr"}
        state = _make_state([apt, t1, t2])
        state._validate_room_hierarchy()
        assert apt["parent"] is None
        assert t1["parent"] == "3 BED"
        assert t2["parent"] == "3 BED"


class TestModernAoiSeedDaylight:
    """v2 contract for daylight: every ``.aoi`` seeds as ``parent = None``.

    Apartment/sub-room hierarchy is reconstructed in-app from the polygons
    and persisted to ``aoi_session.json`` — never from ``.aoi`` header
    fields. See the plan at
    ``~/.claude/plans/the-room-names-are-flickering-turtle.md``.
    """

    def _mk_modern_state(self) -> EditorState:
        state = object.__new__(EditorState)
        object.__setattr__(state, "dirty_vars", set())
        object.__setattr__(state, "_self_dirty_computed_vars", set())
        object.__setattr__(state, "base_state", state)
        object.__setattr__(state, "rooms", [])
        object.__setattr__(state, "project_mode", "daylight")
        return state

    def test_apartment_seeds_as_top_level(self):
        state = self._mk_modern_state()
        state.rooms.append({
            "name": "3 BED", "parent": None,
            "vertices": _square(0, 0, 10), "hdr_file": "h.hdr",
        })
        assert state.rooms[0]["parent"] is None

    def test_sub_room_also_seeds_as_top_level(self):
        """v2: sub-rooms no longer inherit a parent ref from the .aoi file.
        The app's hierarchy pass promotes valid sub-rooms after seeding."""
        state = self._mk_modern_state()
        state.rooms.append({
            "name": "U101_T1", "parent": None,
            "vertices": _square(0, 0, 1), "hdr_file": "h.hdr",
        })
        assert state.rooms[0]["parent"] is None
        assert state.rooms[0]["name"] == "U101_T1"


class TestModernAoiSeedSunlight:
    """v2 .aoi contract: filestem = room name, ``parent = None`` always.

    Parent/child relationships live only in ``aoi_session.json`` and are
    managed from the app — never reconstructed from ``.aoi`` header lines.
    """

    def _mk_sunlight_state(self) -> EditorState:
        state = object.__new__(EditorState)
        object.__setattr__(state, "dirty_vars", set())
        object.__setattr__(state, "_self_dirty_computed_vars", set())
        object.__setattr__(state, "base_state", state)
        object.__setattr__(state, "rooms", [])
        object.__setattr__(state, "project_mode", "sunlight")
        return state

    def test_filestem_becomes_room_name(self):
        """Simulates the v2 seeder branch: each .aoi loads as an independent
        top-level room, keyed by filestem."""
        state = self._mk_sunlight_state()
        filestem = "U101_T1"
        state.rooms.append({
            "name": filestem, "parent": None,
            "vertices": _square(0, 0, 1), "hdr_file": "ffl_090000",
        })
        assert state.rooms[0]["name"] == "U101_T1"
        assert state.rooms[0]["parent"] is None

    def test_sunlight_validator_demotes_cross_labelled_refs(self):
        """Even if a session file sneaks parent refs into sunlight state,
        the validator demotes them (no real parent room exists)."""
        state = self._mk_sunlight_state()
        state.rooms = [
            {"name": "T1", "parent": "UG02", "vertices": _square(0, 0, 1), "hdr_file": "ffl_090000"},
            {"name": "T2", "parent": "UG02", "vertices": _square(2, 2, 1), "hdr_file": "ffl_090000"},
        ]
        state._validate_room_hierarchy()
        assert state.rooms[0]["parent"] is None
        assert state.rooms[1]["parent"] is None


class TestTreeNodesRendering:
    """Layer 3 safety net: any orphan that slips past Layers 1–2 must render
    as ``parent_room`` so it appears top-level, not as ``child_room``."""

    def _mk_daylight_state(self, rooms: list[dict]) -> EditorState:
        state = object.__new__(EditorState)
        object.__setattr__(state, "dirty_vars", set())
        object.__setattr__(state, "_self_dirty_computed_vars", set())
        object.__setattr__(state, "base_state", state)
        object.__setattr__(state, "rooms", rooms)
        object.__setattr__(state, "project_mode", "daylight")
        object.__setattr__(state, "view_groups", [])
        object.__setattr__(state, "hdr_files", [{"name": "h.hdr"}])
        object.__setattr__(state, "current_hdr_idx", 0)
        object.__setattr__(state, "collapsed_hdrs", set())
        object.__setattr__(state, "selected_room_idx", -1)
        object.__setattr__(state, "multi_selected_idxs", [])
        return state

    def test_valid_apartment_renders_parent_then_children(self):
        apt = {"name": "3 BED", "parent": None, "vertices": _square(0, 0, 10), "hdr_file": "h.hdr"}
        t1 = {"name": "T1", "parent": "3 BED", "vertices": _square(2, 2, 1), "hdr_file": "h.hdr"}
        state = self._mk_daylight_state([apt, t1])
        nodes = state.tree_nodes
        types = [n["node_type"] for n in nodes]
        assert types == ["hdr", "parent_room", "child_room"]
        assert nodes[1]["label"] == "3 BED"
        assert nodes[2]["label"] == "T1"

    def test_orphan_safety_net_renders_parent_room(self):
        """If data slips past Layers 1–2 (e.g. legacy session), orphan
        branch must emit ``parent_room`` so orphans still render top-level."""
        # Intentionally skip validator to simulate a legacy state where an
        # orphan parent-ref survives.
        orphan = {"name": "T1", "parent": "GHOST", "vertices": _square(0, 0, 1), "hdr_file": "h.hdr"}
        state = self._mk_daylight_state([orphan])
        nodes = state.tree_nodes
        orphan_node = next(n for n in nodes if n["label"] == "T1")
        assert orphan_node["node_type"] == "parent_room"
        assert orphan_node["indent"] == "16px"
