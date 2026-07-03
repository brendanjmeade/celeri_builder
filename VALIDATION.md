# Validation

How celeri_builder is validated against celeri_ui, and the intentional
behavioral differences between them.

## Test layers

| Layer | Command | When |
| --- | --- | --- |
| Unit/engine (round-trip + actions) | `uv run pytest` | every commit (CI) |
| UI scenarios (Playwright) | `uv run pytest -m ui` | milestone gates, on-demand CI |
| Side-by-side parity vs celeri_ui | `uv run pytest -m parity` | local only (needs celeri_ui dev server + Mapbox token) |

Example data comes from the sibling `celeri_build/data/` tree (override with
`CELERI_DATA_DIR`). UI tests run tokenless (`CELERI_BUILDER_NO_BASEMAP=1`)
with a pinned camera (japan, 140/37.5, zoom 5) and read a hidden
`test-probe` DOM node maintained when `CELERI_BUILDER_TESTING=1`.

## Intentional differences vs celeri_ui

| Behavior | celeri_ui | celeri_builder | Rationale |
| --- | --- | --- | --- |
| Unknown config JSON keys | Dropped on save (only its 59 defaultCommand keys survive) | All keys preserved, order kept | celeri consumes keys the UI doesn't know (`solve_type`, `elastic_operator_cache_dir`, `iterative_coupling_*`, ...); dropping them is data loss |
| Config JSON formatting | Minified `JSON.stringify` | `indent=4` + trailing newline | Human-diffable files |
| Relative path resolution | Broken string munging (`../`→``, `data/`→`../`); cannot resolve the example configs | Resolved against the config file's directory | Correctness |
| Missing referenced file | Silently created empty | `FileNotFoundError` | Silent empty datasets hide errors |
| Gmsh MSH parsing | Regex on positional node order; breaks on non-sequential tags | Real MSH 4.1 parser with tag→coordinate map | japan.msh tags are non-sequential (2, 22, 25, ...) — celeri_ui's mapping is approximate |
| CSV trailing newline | Absent | Present | POSIX text files |
| Numeric-looking names (`007`, `1.50`) | Coerced to numbers (`7`, `1.5`) | Kept as strings when coercion loses information | Losslessness |
| Column canonicalization | Reshapes to its field list, dropping unknown columns | Canonical celeri order first, then unknown columns preserved in original order | celeri's real files carry more columns than the UI models |
| File open/save in undo history | Undoable (FileHandles slice inside redux-undo) | Not undoable | Undo changing which file a save targets is a footgun |
| Mesh display | Only `.msh` files celeri_ui's parser accepts | Same read-only meshes, correct parser | — |

Byte-level compatibilities kept: canonical column order matches celeri;
columns whose name contains `lon`/`lat` are written with exactly 6 decimals;
vertex dedup uses `floor(coord * 1e6)` cells with first-occurrence snapping;
0–360 longitude normalization; segment read defaults are 0/`""` (not the
new-segment defaults), matching celeri_ui.

## Gate log

| Milestone | Date | Result |
| --- | --- | --- |
| M0 widget spike | 2026-07-02 | 12/12 checks (carto + blank basemap); 2000-line push 0.14 s |
| M1 file I/O + display | 2026-07-02 | 136 unit tests green (japan+wna); S1 (open → all layers render, counts match CSVs) and S2 (display toggles) green; parity P0 deferred until the parity driver lands (needs Mapbox token for celeri_ui) |

## Data facts pinned by tests

- japan: 1626 segments, 4 meshes (nankai, japan, sagami, japan_mock_cmi)
- celeri_ui `defaultCommand` has 59 keys (not 63 as first estimated)
- dip-projection horizontal offset = `locking_depth / tan(dip)` (mocha
  constant −0.008993203637245385° reproduced exactly)
- japan and wna station CSVs and japan block CSV carry a trailing empty
  column; wna block does not
