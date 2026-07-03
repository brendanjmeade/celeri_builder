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
| Lasso point-in-polygon | turf `pointsWithinPolygon` | stdlib even-odd ray cast (`geo/polygon.py`) | No turf dependency; verified equivalent against the mocha `PointUtilities` fixture and a matplotlib `Path.contains_points` oracle; boundary points left undefined |
| Hover popups | Mapbox GL popups | deck.gl per-row `tooltip` HTML (name + a couple of key facts) | Widget is deck-native; no Mapbox popup API |
| Map text labels | bare Mapbox symbol text | deck `TextLayer` with small pixel offset + translucent background box, `%g` formatting | Legibility over the basemap; same `plottableKey` semantics |

Byte-level compatibilities kept: canonical column order matches celeri;
columns whose name contains `lon`/`lat` are written with exactly 6 decimals;
vertex dedup uses `floor(coord * 1e6)` cells with first-occurrence snapping;
0–360 longitude normalization; segment read defaults are 0/`""` (not the
new-segment defaults), matching celeri_ui.

## Side-by-side parity (P0–P6)

`tests/parity/` replays identical **abstract edit scripts** (data, not code)
against *both* the celeri_builder engine and the live celeri_ui web app, then
compares the saved files. Scripts are lists of `(op, params)` tuples keyed on
segment **names** and **coordinates** (never row indices / vertex ids), so
each side resolves them against its own state.

| Script | Edit | Builder-side contract asserted |
| --- | --- | --- |
| P0 | open → save, no edits | canonicalization only (semantic round-trip) |
| P1 | bulk dip = 60 on `aleun`, `alu_1` | both dips 60 in saved CSV; counts unchanged |
| P2 | create segment from two coords | +1 segment, +2 vertices, `new_segment` present |
| P3 | move a vertex to an empty coord | counts unchanged |
| P3\_automerge | move a vertex onto another vertex | −1 vertex (occupant merged) |
| P4 | delete `aleun`, `alu_1` | −2 segments; both names gone; endpoint GC |
| P5 | split `alu_2a` at its midpoint | +1 segment; `alu_2a_a`/`alu_2a_b` present |
| P6 | P1 edits then full undo | saved files **byte-identical** to P0 |

Op vocabulary: `edit_segments {names, patch}`, `create_segment {start, end}`,
`move_vertex {at, to}` (auto-merges when `to` lands on an occupied vertex
cell), `delete_segments {names}`, `split_segment {name}`, `undo_all {}`.

**Two independent halves.** The **builder half** (`drive_builder.py`) imports
the pure model layer directly (`load_project` → `Store` → resolve abstract
ops to actions → `reduce` → `save_project`) and runs **anywhere** — it is the
runnable core and gates M4. The **celeri_ui half** (`drive_celeri_ui.py`) is a
Playwright driver that is **deferred** to a token-equipped local run: in this
environment celeri_ui has no `node_modules` and there is no Mapbox token, so
it **skips cleanly** with the concrete reason.

**Comparator.** Both outputs are loaded with `celeri_builder.io`; values are
compared on the **column intersection** with float tolerance `1e-6`. A
`NORMALIZATIONS` table encodes every *documented* intentional difference so
any *undocumented* divergence fails loudly. celeri_builder may be a **superset**
(extra canonical columns) but must never drop or corrupt data celeri_ui keeps.

| Normalization | What the comparator tolerates | Source difference |
| --- | --- | --- |
| Synthesized segment columns | `ss_reg_flag`, `ds_reg_flag`, `ts_reg_flag`, `slip_rate_bound_sigma` present in builder, absent in celeri_ui | builder writes the full 33-col canonical order; celeri_ui's field list is narrower |
| Numeric-name coercion | `name` compared as string with numeric equivalence (`"2"` ≡ `2`) | celeri_ui coerces numeric-looking names to numbers; builder keeps them lossless |
| Trailing newline | ignored (tabular parse strips it) | builder writes one, celeri_ui does not |
| Command / config JSON | **not compared** for celeri_ui | celeri_ui's command-file save is disabled (`App.tsx`); builder rewrites it (indent 4, all keys) |
| Path resolution | inputs flattened to one dir + `*_file_name` rewritten to bare filenames for celeri_ui | celeri_ui's `GetProjectFile` cannot resolve `../segment/...` against its in-memory FS |
| Row order | compared positionally | both preserve input order |

**celeri_ui workaround (deferred half).** `drive_celeri_ui` starts
`npm run dev`, opens Chromium at `localhost:3000/?fake-dir`, and injects
`window.FakeDirectory` (`page.add_init_script`) with the region files
**flattened into one directory** and the config `*_file_name` fields rewritten
to bare filenames. Edits are driven via celeri_ui `data-testid` selectors and
synthetic Mapbox-canvas clicks computed with the **same web-mercator pixel
math** as the builder UI tests (pinned view japan 140/37.5 z5); saved files are
read back out of `window.FakeDirectory` via `page.evaluate`. The map-pixel /
selector flows are exercised for the first time on the local token-equipped run
(calibration point).

### Running parity locally

```bash
cd celeri_ui && npm install          # one-time; provides node_modules
echo "VITE_MAPBOX_TOKEN=pk.…" > celeri_ui/.env   # or export CELERI_UI_MAPBOX_TOKEN
cd celeri_builder
uv run pytest -m parity -rs          # both halves; -rs prints skip reasons
```

Without a token / `node_modules`, the same command runs the **builder half**
(P0–P6 pass) and **skips** the celeri_ui half with a clear reason — a useful
regression that runs in CI and offline. `drive_builder` and the abstract
scripts have no browser dependency.

## Gate log

| Milestone | Date | Result |
| --- | --- | --- |
| M0 widget spike | 2026-07-02 | 12/12 checks (carto + blank basemap); 2000-line push 0.14 s |
| M1 file I/O + display | 2026-07-02 | 136 unit tests green (japan+wna); S1 (open → all layers render, counts match CSVs) and S2 (display toggles) green; parity P0 deferred until the parity driver lands (needs Mapbox token for celeri_ui) |
| M2 store + selection + panels | 2026-07-02 | 29 reducers + snapshot-undo Store; MapController select dispatch; inspector + 8 panels + editable_item (multi-select `'-'`, 1 s debounce). 319 unit tests green; S1–S4 UI green. |
| M3 geometry editing | 2026-07-02 | Edit modes + mode banner + full interaction table: drag (MoveVertex/Block/Velocity on dragend, auto-merge), two-click segment / one-click block+velocity create, vertex merge/bridge/extrude/split, delete + vertex GC, SceneBuilder partial group updates. 334 unit tests green; S1–S7 UI green. |
| M4 features + polish | 2026-07-03 | Lasso close (even-odd ray cast, point-in-polygon oracle-checked vs matplotlib), per-panel text labels (`plottableKey`), hover tooltips, style-picker. 350 unit tests green (+16 lasso/label); S1–S10 UI green (S8 lasso / S9 undo / S10 save). ruff clean. |
| M4 parity harness | 2026-07-03 | `tests/parity/` landed. Builder-side replay of P0–P6 (+ P3 auto-merge) green (`uv run pytest -m parity` → 8 passed); celeri_ui-side skips cleanly (no `node_modules` / token in this env). `drive_builder` + abstract scripts run anywhere; live celeri_ui comparison deferred to a token-equipped local run. ruff clean on `tests/parity`. |
| M4 integration verify | 2026-07-03 | Full suite green in this env: `tests/unit` 350 passed, `tests/ui -m ui` 10 passed (S1–S10, stable over 2 consecutive runs), `tests/parity -m parity` 8 passed + 8 clean skips, `uv run pytest -q` 350 passed / 26 deselected. Headless app boot in `CELERI_BUILDER_TESTING=1` confirms `deck_layers_labels` state var and all 10 layer-group vars build without error. ruff clean on `src tests`. |

## Data facts pinned by tests

- japan: 481 segments, 462 deduped vertices, 21 blocks, 2176 velocities, 4
  meshes (nankai, japan, sagami, japan_mock_cmi) — pinned by the parity
  scripts (P2 → 482/464, P4 → 479, P5 → 482)
- celeri_ui `defaultCommand` has 59 keys (not 63 as first estimated)
- dip-projection horizontal offset = `locking_depth / tan(dip)` (mocha
  constant −0.008993203637245385° reproduced exactly)
- japan and wna station CSVs and japan block CSV carry a trailing empty
  column; wna block does not
