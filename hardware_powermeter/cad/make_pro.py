#!/usr/bin/env python3
"""Write pmeter.kicad_pro: the project, and the rules the board is checked by.

Without a project file KiCad checks the board against its own defaults, and
those defaults are not this board's. Two of them matter here:

  clearance 0.2 mm     the default. The fine pitch parts on this board do not
                       fit it: the 0,4 mm bumps of the TPS22916 sit 0,17 mm
                       apart and the module's LGA pads 0,55 mm; so the rule
                       is the fabricator's 0,127, not KiCad's default.
  hole clearance 0.25  same story, on the Tag-Connect's locating holes.

What is written below is the capability of a normal four layer fab - JLCPCB
and PCBWay both quote 0.127 mm track and space and 0.2 mm hole to copper on
this class of board. It is an ASSUMPTION until the fabricator is asked, which
is already an open item of 04-pcb-e-caixa.md: the stackup, the trace width for
50 ohm and the one for 90 ohm differential all wait on the same answer.
"""

from __future__ import annotations

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent

CLEARANCE = 0.127     # mm, track to track and pad to pad
TRACK = 0.15
HOLE_CLEARANCE = 0.2
VIA_D, VIA_DRILL = 0.45, 0.25

PRO = {
    "board": {
        "3dviewports": [],
        "design_settings": {
            "defaults": {
                "board_outline_line_width": 0.1,
                "copper_line_width": 0.15,
                "copper_text_size_h": 1.0,
                "copper_text_size_v": 1.0,
                "copper_text_thickness": 0.15,
                "other_line_width": 0.1,
                "silk_line_width": 0.12,
                "silk_text_size_h": 0.7,
                "silk_text_size_v": 0.7,
                "silk_text_thickness": 0.1,
            },
            "diff_pair_dimensions": [{"gap": 0.2, "via_gap": 0.25, "width": 0.2}],
            "drc_exclusions": [],
            "rule_severities": {
                "copper_edge_clearance": "error",
                "courtyards_overlap": "error",
                "duplicate_footprints": "warning",
                "footprint": "error",
                "hole_clearance": "error",
                "hole_near_hole": "error",
                "malformed_courtyard": "error",
                "missing_courtyard": "ignore",
                "missing_footprint": "warning",
                "silk_over_copper": "ignore",
                "silk_overlap": "ignore",
                "unconnected_items": "warning",
                "zones_intersect": "error",
            },
            "rules": {
                "allow_blind_buried_vias": False,
                "allow_microvias": False,
                "max_error": 0.005,
                "min_clearance": CLEARANCE,
                "min_connection": 0.0,
                "min_copper_edge_clearance": 0.3,
                "min_hole_clearance": HOLE_CLEARANCE,
                "min_hole_to_hole": 0.2,
                "min_microvia_diameter": 0.2,
                "min_microvia_drill": 0.1,
                "min_resolved_spokes": 2,
                "min_silk_clearance": 0.0,
                "min_text_height": 0.6,
                "min_text_thickness": 0.08,
                "min_through_hole_diameter": 0.2,
                "min_track_width": 0.127,
                "min_via_annular_width": 0.1,
                "min_via_diameter": 0.4,
                "solder_mask_to_copper_clearance": 0.0,
                "use_height_for_length_calcs": True,
            },
            "track_widths": [0.0, TRACK, 0.25, 0.4, 0.8],
            "via_dimensions": [{"diameter": 0.0, "drill": 0.0},
                               {"diameter": VIA_D, "drill": VIA_DRILL}],
            "zones_allow_external_fillets": False,
        },
        "layer_presets": [],
        "viewports": [],
    },
    "boards": [],
    "cvpcb": {"equivalence_files": []},
    "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
    "meta": {"filename": "pmeter.kicad_pro", "version": 1},
    "net_settings": {
        "classes": [
            {
                "bus_width": 12.0, "clearance": CLEARANCE,
                "diff_pair_gap": 0.2, "diff_pair_via_gap": 0.25,
                "diff_pair_width": 0.2, "line_style": 0,
                "microvia_diameter": 0.2, "microvia_drill": 0.1,
                "name": "Default",
                "pcb_color": "rgba(0, 0, 0, 0.000)",
                "schematic_color": "rgba(0, 0, 0, 0.000)",
                "track_width": TRACK, "via_diameter": VIA_D, "via_drill": VIA_DRILL,
                "wire_width": 6.0,
            },
            {
                "bus_width": 12.0, "clearance": CLEARANCE,
                "diff_pair_gap": 0.2, "diff_pair_via_gap": 0.25,
                "diff_pair_width": 0.2, "line_style": 0,
                "microvia_diameter": 0.2, "microvia_drill": 0.1,
                "name": "Alimentacao",
                "pcb_color": "rgba(0, 0, 0, 0.000)",
                "schematic_color": "rgba(0, 0, 0, 0.000)",
                "track_width": 0.4, "via_diameter": 0.6, "via_drill": 0.3,
                "wire_width": 6.0,
            },
            {
                # 0,127 and not the bike computer's 0,2 (2026-09-27): the
                # USB here is full speed on 3 cm of track, the pair keeps
                # its calculated width, and 0,2 of clearance closed every
                # 0,5 mm pitch escape in route.py (FOLGA_USB says the same)
                "bus_width": 12.0, "clearance": 0.127,
                "diff_pair_gap": 0.2, "diff_pair_via_gap": 0.25,
                "diff_pair_width": 0.2, "line_style": 0,
                "microvia_diameter": 0.2, "microvia_drill": 0.1,
                "name": "USB",
                "pcb_color": "rgba(0, 0, 0, 0.000)",
                "schematic_color": "rgba(0, 0, 0, 0.000)",
                "track_width": 0.2, "via_diameter": VIA_D, "via_drill": VIA_DRILL,
                "wire_width": 6.0,
            },
        ],
        "meta": {"version": 3},
        "net_colors": None,
        "netclass_assignments": None,
        "netclass_patterns": [
            {"netclass": "Alimentacao", "pattern": "GND"},
            {"netclass": "Alimentacao", "pattern": "VSYS"},
            {"netclass": "Alimentacao", "pattern": "VBAT"},
            {"netclass": "Alimentacao", "pattern": "VBUS"},
            {"netclass": "Alimentacao", "pattern": "3V0*"},
            {"netclass": "USB", "pattern": "USB_D*"},
        ],
    },
    "pcbnew": {"last_paths": {}, "page_layout_descr_file": ""},
    "schematic": {
        "legacy_lib_dir": "", "legacy_lib_list": [],
        "meta": {"version": 1},
        "page_layout_descr_file": "",
    },
    "sheets": [],
    "text_variables": {},
}


def main() -> int:
    caminho = HERE / "pmeter.kicad_pro"
    caminho.write_text(json.dumps(PRO, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8", newline="\n")
    print(f"{caminho.name}: isolamento {CLEARANCE} mm, trilha {TRACK} mm, "
          f"furo a cobre {HOLE_CLEARANCE} mm, 3 classes de rede")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
