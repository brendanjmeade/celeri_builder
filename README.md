# celeri_builder

Interactive map editor for [celeri](https://github.com/brendanjmeade/celeri)
kinematic earthquake cycle model inputs — a Python/[Trame](https://kitware.github.io/trame/)
+ [deck.gl](https://deck.gl/) rewrite of
[celeri_ui](https://github.com/brendanjmeade/celeri_ui).

![celeri_builder editing the Japan model](docs/screenshot.png)

## Features

- **Edit on the map** — draw and drag fault segments (a shared-vertex graph),
  blocks, and station velocities; merge, bridge, extrude, and split vertices.
- **Select** by click, shift-click, or lasso, and bulk-edit properties across a
  selection.
- **Lossless round-trip** of celeri input files (segments, blocks, stations,
  meshes, config JSON) — unknown columns and config keys are preserved.
- **Undo/redo** for every edit.
- Runs in the browser, as a desktop window (`celeri-builder --app`), or offline.

## Quick start

```console
pip install celeri_builder
celeri-builder
```

Base maps use Mapbox when a token is available — set
`CELERI_BUILDER_MAPBOX_TOKEN` in your shell or a local `.env`. Without one, the
app falls back to a public Carto basemap; with no network it runs on a blank
background and stays fully functional.

## Development

```console
uv venv && source .venv/bin/activate
uv pip install -e .
uv sync --all-extras --dev

uv run pytest              # unit + engine suite
uv run pytest -m ui        # browser UI tests (run: playwright install chromium)
uv run pytest -m parity    # side-by-side vs celeri_ui (local only)
uv run pre-commit run --all-files
```

The custom deck.gl map widget ships pinned copies of deck.gl 9.3.6 (MIT) and
MapLibre GL JS 5.24.0 (BSD-3-Clause) under
`src/celeri_builder/widgets/module/serve/`, so the app never loads code from a
CDN. Releases follow [conventional commits](https://www.conventionalcommits.org/).

## License

MIT — see [LICENSE](LICENSE).
