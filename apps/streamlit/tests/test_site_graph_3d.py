"""Unit tests for the pure 3D site-graph model builder and viewer labels."""

from __future__ import annotations

import json

from app_support.site_graph_3d.graph_data import build_site_graph_model
from app_support.site_graph_3d.viewer_assembler import (
    TEXTURE_CDN_BASE,
    THREE_CDN_BASE,
    build_viewer_html,
)
from app_support.site_graph_3d.viewer_labels import (
    VIEWER_LABELS_EN,
    VIEWER_LABELS_ID,
    viewer_labels,
)


def _jsonl(*records: dict[str, object]) -> str:
    return "\n".join(json.dumps(record) for record in records)


def _node_by_id(model: dict[str, object], node_id: str) -> dict[str, object]:
    nodes = model["nodes"]
    assert isinstance(nodes, list)
    for node in nodes:
        if node["id"] == node_id:
            return node
    raise AssertionError(f"node {node_id!r} not found")


# Risk: a seed page (discovered_from null) must render as the central Sun. Verify
# it is flagged is_root and collected into root_ids. Type: unit.
def test_root_page_is_flagged_and_collected() -> None:
    model = build_site_graph_model(
        _jsonl(
            {
                "url": "https://x.com",
                "discovered_from": None,
                "page_size_kb": 5.0,
                "status": "success",
                "depth": 0,
                "round_num": 1,
            },
        )
    )
    root = _node_by_id(model, "https://x.com")
    assert root["is_root"] is True
    assert model["root_ids"] == ["https://x.com"]


# Risk: planet linking + the richness signal both depend on counting how many
# pages were discovered from a page. Verify child_count reflects resolvable
# children only. Type: unit.
def test_child_count_reflects_discovered_children() -> None:
    model = build_site_graph_model(
        _jsonl(
            {
                "url": "https://x.com",
                "discovered_from": None,
                "page_size_kb": 5.0,
                "status": "success",
                "depth": 0,
                "round_num": 1,
            },
            {
                "url": "https://x.com/a",
                "discovered_from": "https://x.com",
                "page_size_kb": 1.0,
                "status": "success",
                "depth": 1,
                "round_num": 1,
            },
            {
                "url": "https://x.com/b",
                "discovered_from": "https://x.com",
                "page_size_kb": 1.0,
                "status": "success",
                "depth": 1,
                "round_num": 1,
            },
        )
    )
    assert _node_by_id(model, "https://x.com")["child_count"] == 2
    assert _node_by_id(model, "https://x.com/a")["child_count"] == 0


# Risk: planet size must scale with page weight. Verify min-max normalisation
# maps the smallest present page to 0, the largest to 1, and the middle between.
# Type: unit.
def test_size_scale_is_min_max_normalised() -> None:
    model = build_site_graph_model(
        _jsonl(
            {
                "url": "https://x.com",
                "discovered_from": None,
                "page_size_kb": 30.0,
                "status": "success",
                "depth": 0,
                "round_num": 1,
            },
            {
                "url": "https://x.com/a",
                "discovered_from": "https://x.com",
                "page_size_kb": 10.0,
                "status": "success",
                "depth": 1,
                "round_num": 1,
            },
            {
                "url": "https://x.com/b",
                "discovered_from": "https://x.com",
                "page_size_kb": 20.0,
                "status": "success",
                "depth": 1,
                "round_num": 1,
            },
        )
    )
    assert _node_by_id(model, "https://x.com")["size_scale"] == 1.0
    assert _node_by_id(model, "https://x.com/a")["size_scale"] == 0.0
    assert _node_by_id(model, "https://x.com/b")["size_scale"] == 0.5


# Risk: pages with equal weight must not all collapse to size 0 (invisible).
# Verify identical sizes map to the uniform mid scale. Type: unit.
def test_uniform_sizes_use_mid_scale() -> None:
    model = build_site_graph_model(
        _jsonl(
            {
                "url": "https://x.com/a",
                "discovered_from": None,
                "page_size_kb": 7.0,
                "status": "success",
                "depth": 0,
                "round_num": 1,
            },
            {
                "url": "https://x.com/b",
                "discovered_from": None,
                "page_size_kb": 7.0,
                "status": "success",
                "depth": 0,
                "round_num": 1,
            },
        )
    )
    assert _node_by_id(model, "https://x.com/a")["size_scale"] == 0.5
    assert _node_by_id(model, "https://x.com/b")["size_scale"] == 0.5


# Risk: a failed/skipped page has no page_size_kb; it must still yield a node
# with a zero (smallest) size rather than crashing. Type: unit.
def test_missing_page_size_maps_to_zero_scale() -> None:
    model = build_site_graph_model(
        _jsonl(
            {
                "url": "https://x.com",
                "discovered_from": None,
                "page_size_kb": 5.0,
                "status": "success",
                "depth": 0,
                "round_num": 1,
            },
            {
                "url": "https://x.com/fail",
                "discovered_from": "https://x.com",
                "page_size_kb": None,
                "status": "fail",
                "depth": 1,
                "round_num": 3,
            },
        )
    )
    failed = _node_by_id(model, "https://x.com/fail")
    assert failed["page_size_kb"] is None
    assert failed["size_scale"] == 0.0


# Risk: richness drives the lush-vs-barren look; it must blend size and outward
# links with the documented weights. Verify a rich hub and a bare leaf. Type: unit.
def test_richness_blends_size_and_links() -> None:
    model = build_site_graph_model(
        _jsonl(
            {
                "url": "https://x.com",
                "discovered_from": None,
                "page_size_kb": 30.0,
                "status": "success",
                "depth": 0,
                "round_num": 1,
            },
            {
                "url": "https://x.com/a",
                "discovered_from": "https://x.com",
                "page_size_kb": 10.0,
                "status": "success",
                "depth": 1,
                "round_num": 1,
            },
            {
                "url": "https://x.com/b",
                "discovered_from": "https://x.com",
                "page_size_kb": 20.0,
                "status": "success",
                "depth": 1,
                "round_num": 1,
            },
        )
    )
    # Hub: size_scale 1.0, links 2/2=1.0 -> 0.6 + 0.4 = 1.0
    assert _node_by_id(model, "https://x.com")["richness"] == 1.0
    # Leaf a: size_scale 0.0, no children -> 0.0
    assert _node_by_id(model, "https://x.com/a")["richness"] == 0.0


# Risk: the biggest pages should read as ringed gas giants. Verify is_giant
# trips only above the size threshold. Type: unit.
def test_is_giant_only_for_largest_pages() -> None:
    model = build_site_graph_model(
        _jsonl(
            {
                "url": "https://x.com",
                "discovered_from": None,
                "page_size_kb": 100.0,
                "status": "success",
                "depth": 0,
                "round_num": 1,
            },
            {
                "url": "https://x.com/a",
                "discovered_from": "https://x.com",
                "page_size_kb": 1.0,
                "status": "success",
                "depth": 1,
                "round_num": 1,
            },
        )
    )
    assert _node_by_id(model, "https://x.com")["is_giant"] is True
    assert _node_by_id(model, "https://x.com/a")["is_giant"] is False


# Risk: planet colour must come from crawl status, with an unknown status falling
# back to the neutral tint (never an error colour). Type: unit.
def test_color_category_from_status_with_neutral_fallback() -> None:
    model = build_site_graph_model(
        _jsonl(
            {
                "url": "https://x.com/ok",
                "discovered_from": None,
                "page_size_kb": 1.0,
                "status": "success",
                "depth": 0,
                "round_num": 1,
            },
            {
                "url": "https://x.com/bad",
                "discovered_from": None,
                "page_size_kb": None,
                "status": "fail",
                "depth": 0,
                "round_num": 1,
            },
            {
                "url": "https://x.com/new",
                "discovered_from": None,
                "page_size_kb": None,
                "status": "mystery",
                "depth": 0,
                "round_num": None,
            },
        )
    )
    assert _node_by_id(model, "https://x.com/ok")["color_category"] == "success"
    assert _node_by_id(model, "https://x.com/bad")["color_category"] == "fail"
    assert _node_by_id(model, "https://x.com/new")["color_category"] == "discovered"


# Risk: the yellow "retried" accent must trip only past the initial round. Verify
# round 1 and null are not retries but round 3 is. Type: unit.
def test_retry_flag_trips_past_initial_round() -> None:
    model = build_site_graph_model(
        _jsonl(
            {
                "url": "https://x.com/first",
                "discovered_from": None,
                "page_size_kb": 1.0,
                "status": "success",
                "depth": 0,
                "round_num": 1,
            },
            {
                "url": "https://x.com/retried",
                "discovered_from": None,
                "page_size_kb": 1.0,
                "status": "success",
                "depth": 0,
                "round_num": 3,
            },
            {
                "url": "https://x.com/pending",
                "discovered_from": None,
                "page_size_kb": None,
                "status": "discovered",
                "depth": 0,
                "round_num": None,
            },
        )
    )
    assert _node_by_id(model, "https://x.com/first")["retry"] is False
    assert _node_by_id(model, "https://x.com/retried")["retry"] is True
    assert _node_by_id(model, "https://x.com/pending")["retry"] is False


# Risk: a link line must connect each child to its parent. Verify edges list the
# resolvable parent -> child pairs. Type: unit.
def test_edges_connect_children_to_parents() -> None:
    model = build_site_graph_model(
        _jsonl(
            {
                "url": "https://x.com",
                "discovered_from": None,
                "page_size_kb": 5.0,
                "status": "success",
                "depth": 0,
                "round_num": 1,
            },
            {
                "url": "https://x.com/a",
                "discovered_from": "https://x.com",
                "page_size_kb": 1.0,
                "status": "success",
                "depth": 1,
                "round_num": 1,
            },
        )
    )
    assert model["edges"] == [{"source": "https://x.com", "target": "https://x.com/a"}]


# Risk: a page whose parent is not in the log (dangling) must not invent an edge
# or a false root; the raw discovered_from stays for the tooltip. Type: unit.
def test_dangling_parent_yields_no_edge_and_no_false_root() -> None:
    model = build_site_graph_model(
        _jsonl(
            {
                "url": "https://x.com/orphan",
                "discovered_from": "https://gone.com",
                "page_size_kb": 1.0,
                "status": "success",
                "depth": 2,
                "round_num": 1,
            },
        )
    )
    orphan = _node_by_id(model, "https://x.com/orphan")
    assert orphan["parent"] is None
    assert orphan["is_root"] is False
    assert orphan["discovered_from"] == "https://gone.com"
    assert model["edges"] == []
    assert model["root_ids"] == []


# Risk: a partially written or corrupt log must still render. Verify blank and
# non-JSON lines are skipped, not fatal. Type: unit.
def test_malformed_lines_are_skipped() -> None:
    text = "\n".join(
        [
            "",
            "not json",
            json.dumps(
                {
                    "url": "https://x.com",
                    "discovered_from": None,
                    "page_size_kb": 1.0,
                    "status": "success",
                    "depth": 0,
                    "round_num": 1,
                }
            ),
            "   ",
        ]
    )
    model = build_site_graph_model(text)
    assert model["stats"]["total"] == 1
    assert _node_by_id(model, "https://x.com")["is_root"] is True


# Risk: the recorder writes one line per URL, but a re-read must be resilient to
# duplicates; the last record for a URL should win. Type: unit.
def test_duplicate_url_keeps_last_record() -> None:
    model = build_site_graph_model(
        _jsonl(
            {
                "url": "https://x.com",
                "discovered_from": None,
                "page_size_kb": 1.0,
                "status": "discovered",
                "depth": 0,
                "round_num": None,
            },
            {
                "url": "https://x.com",
                "discovered_from": None,
                "page_size_kb": 9.0,
                "status": "success",
                "depth": 0,
                "round_num": 1,
            },
        )
    )
    assert model["stats"]["total"] == 1
    assert _node_by_id(model, "https://x.com")["status"] == "success"


# Risk: an empty log must return an empty, well-formed model rather than raising.
# Type: unit.
def test_empty_input_returns_empty_model() -> None:
    model = build_site_graph_model("")
    assert model["nodes"] == []
    assert model["edges"] == []
    assert model["root_ids"] == []
    assert model["stats"] == {"total": 0, "by_status": {}, "max_depth": 0}


# Risk: the viewer HUD summarises the crawl; stats must count statuses and the
# deepest ring. Type: unit.
def test_stats_summarise_statuses_and_depth() -> None:
    model = build_site_graph_model(
        _jsonl(
            {
                "url": "https://x.com",
                "discovered_from": None,
                "page_size_kb": 5.0,
                "status": "success",
                "depth": 0,
                "round_num": 1,
            },
            {
                "url": "https://x.com/a",
                "discovered_from": "https://x.com",
                "page_size_kb": None,
                "status": "fail",
                "depth": 1,
                "round_num": 2,
            },
            {
                "url": "https://x.com/b",
                "discovered_from": "https://x.com/a",
                "page_size_kb": 2.0,
                "status": "success",
                "depth": 2,
                "round_num": 1,
            },
        )
    )
    assert model["stats"]["total"] == 3
    assert model["stats"]["by_status"] == {"success": 2, "fail": 1}
    assert model["stats"]["max_depth"] == 2


# Risk: the viewer renders in EN or ID; a key present in one language but missing
# in the other would show a broken label. Verify the catalogs stay in sync.
# Type: unit.
def test_viewer_label_catalogs_have_identical_keys() -> None:
    assert VIEWER_LABELS_EN.keys() == VIEWER_LABELS_ID.keys()


# Risk: an empty label would render as a blank control/field. Verify every label
# in both languages is non-empty. Type: unit.
def test_viewer_labels_have_no_empty_values() -> None:
    for language, catalog in (("en", VIEWER_LABELS_EN), ("id", VIEWER_LABELS_ID)):
        for key, value in catalog.items():
            assert value, f"[{language}] viewer label {key!r} is empty"


# Risk: an unknown or blank language must not crash the launcher; it should fall
# back to English. Verify the resolver's language handling. Type: unit.
def test_viewer_labels_resolver_falls_back_to_english() -> None:
    assert viewer_labels("id") is VIEWER_LABELS_ID
    assert viewer_labels("ID") is VIEWER_LABELS_ID
    assert viewer_labels("en") is VIEWER_LABELS_EN
    assert viewer_labels("fr") is VIEWER_LABELS_EN
    assert viewer_labels("") is VIEWER_LABELS_EN


# Risk: the new tab is self-contained; the assembled document must embed the
# crawl graph, the localized labels, and the pinned three.js CDN so it renders
# without any further server calls. Type: unit.
def test_build_viewer_html_embeds_graph_labels_and_cdn() -> None:
    html = build_viewer_html(
        _jsonl(
            {
                "url": "https://x.com",
                "discovered_from": None,
                "page_size_kb": 5.0,
                "status": "success",
                "depth": 0,
                "round_num": 1,
            }
        ),
        {"title": "Crawl universe"},
    )
    assert THREE_CDN_BASE in html
    assert "https://x.com" in html  # graph node embedded
    assert "Crawl universe" in html  # localized label embedded
    assert 'id="sg-canvas"' in html  # viewer shell inlined
    assert "three/addons/" in html  # import map wired


# Risk: failed pages render as black holes with a screen-space gravitational-lens
# pass; if the pass or its per-frame projection were dropped the lensing silently
# disappears. Verify the lensing code is inlined into the viewer. Type: unit.
def test_build_viewer_html_includes_black_hole_lensing() -> None:
    html = build_viewer_html(
        _jsonl(
            {
                "url": "https://x.com",
                "discovered_from": None,
                "page_size_kb": 5.0,
                "status": "success",
                "depth": 0,
                "round_num": 1,
            }
        ),
        {},
    )
    assert "postprocessing/ShaderPass.js" in html  # lens pass imported
    assert "blackHoleLensShader" in html  # custom lensing shader inlined
    assert "updateLensUniforms" in html  # per-frame hole projection wired


# Risk: a black hole must read as a dark body (a planet-like mass), not a light
# source. It previously carried a bright additive accretion disc + glow sprite
# whose bloom washed nearby planets orange; if that emitting disc were
# reintroduced the wash returns. Verify the black hole emits no light while its
# gravitational lensing (the ring) stays. Type: unit.
def test_build_viewer_html_black_hole_is_dark_body() -> None:
    html = build_viewer_html(
        _jsonl(
            {
                "url": "https://x.com",
                "discovered_from": None,
                "page_size_kb": 5.0,
                "status": "success",
                "depth": 0,
                "round_num": 1,
            }
        ),
        {},
    )
    assert "makeAccretionDisk" not in html  # no emitting accretion disc
    assert "accretionDisks" not in html  # no disc bookkeeping/animation
    assert "blackHoleLensShader" in html  # gravitational lensing + photon ring kept


# Risk: black holes are dark and hard to spot among many planets, so each carries
# a pulsar-style beacon (two additive beams) pulsed each frame. It must stay a
# pure-geometry effect — no THREE.Light — and be wired into the animation loop; if
# the beacon or its pulse were dropped, failed pages become easy to miss. Type: unit.
def test_build_viewer_html_black_hole_has_pulsar_beacon() -> None:
    html = build_viewer_html(
        _jsonl(
            {
                "url": "https://x.com",
                "discovered_from": None,
                "page_size_kb": 5.0,
                "status": "success",
                "depth": 0,
                "round_num": 1,
            }
        ),
        {},
    )
    assert "makeBlackHoleBeacon" in html  # beacon geometry inlined
    assert "beacons" in html  # beacon bookkeeping present
    assert "BEACON_PULSE_SPEED" in html  # per-frame pulse wired


# Risk: a crawled URL could contain "</script>"; injected verbatim it would break
# out of the bootstrap script tag. Verify the data is escaped, not raw. Type: unit.
def test_build_viewer_html_escapes_script_breakout() -> None:
    html = build_viewer_html(
        _jsonl(
            {
                "url": "https://x.com/</script><b>",
                "discovered_from": None,
                "page_size_kb": 1.0,
                "status": "success",
                "depth": 0,
                "round_num": 1,
            }
        ),
        {},
    )
    assert "https://x.com/</script><b>" not in html  # not injected verbatim
    assert "\\u003c/script>\\u003cb>" in html  # escaped form present


# Risk: the viewer reads the realistic-texture CDN base from a JS global; a
# placeholder/global-name collision would blank it and disable textures. Verify
# the pinned base is injected into the global assignment intact. Type: unit.
def test_build_viewer_html_injects_texture_cdn_base() -> None:
    html = build_viewer_html(
        _jsonl(
            {
                "url": "https://x.com",
                "discovered_from": None,
                "page_size_kb": 1.0,
                "status": "success",
                "depth": 0,
                "round_num": 1,
            }
        ),
        {},
    )
    assert f'window.__TEXTURE_BASE__ = "{TEXTURE_CDN_BASE}"' in html
    assert "window.https://" not in html  # global name not clobbered by the replace


# Risk: the Controls panel must open collapsed so it does not cover the scene on
# first load. Verify the assembled shell marks the help panel collapsed. Type: unit.
def test_build_viewer_html_controls_start_collapsed() -> None:
    html = build_viewer_html(
        _jsonl(
            {
                "url": "https://x.com",
                "discovered_from": None,
                "page_size_kb": 1.0,
                "status": "success",
                "depth": 0,
                "round_num": 1,
            }
        ),
        {},
    )
    assert 'id="sg-help" class="sg-panel" data-collapsed="true"' in html


# Risk: the <h1> paints before the module script localizes it, so a stale "Crawl
# universe" fallback flashes before "Site Orrery". Verify the shell ships the final
# title so there is no swap. Type: unit.
def test_build_viewer_html_title_has_no_placeholder_flash() -> None:
    html = build_viewer_html(
        _jsonl(
            {
                "url": "https://x.com",
                "discovered_from": None,
                "page_size_kb": 1.0,
                "status": "success",
                "depth": 0,
                "round_num": 1,
            }
        ),
        {},
    )
    assert '<h1 id="sg-title">Site Orrery</h1>' in html
    assert "Crawl universe" not in html
