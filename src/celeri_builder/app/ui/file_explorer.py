"""Server-side file browser dialog (open / save-as), celeri_ui FileExplorer
equivalent. Plain trame state; one instance per app.

State keys: fx_open (dialog visible), fx_dir (current dir str), fx_entries
(list of {name, is_dir}), fx_filter (extension like '.json'), fx_mode
('open'|'save'), fx_filename (save-as name), fx_preview (text head of the
selected file), fx_title.
"""

from __future__ import annotations

from pathlib import Path

from trame.widgets import html
from trame.widgets import vuetify3 as v3

PREVIEW_BYTES = 2000


class FileExplorer:
    def __init__(self, app, root: Path):
        self.app = app
        self.root = root.resolve()
        self._callback = None
        state = app.state
        state.fx_open = False
        state.fx_dir = str(self.root)
        state.fx_entries = []
        state.fx_filter = ""
        state.fx_mode = "open"
        state.fx_filename = ""
        state.fx_preview = ""
        state.fx_title = "Open file"

    # -- API ----------------------------------------------------------------
    def open(self, callback, extension="", mode="open", title="Open file"):
        """Show the dialog; callback(Path) fires on selection/save."""
        self._callback = callback
        with self.app.state as state:
            state.fx_filter = extension
            state.fx_mode = mode
            state.fx_title = title
            state.fx_filename = ""
            state.fx_preview = ""
            state.fx_open = True
        self._list_dir(Path(self.app.state.fx_dir))

    # -- handlers -------------------------------------------------------------
    def _list_dir(self, path: Path):
        # ``root`` is only the initial directory; navigation is unrestricted
        # across the local filesystem (the trame server runs on the user's
        # own machine). The filesystem root ('/') bounds the "up" button
        # naturally since Path('/').parent == Path('/').
        path = path.resolve()
        ext = self.app.state.fx_filter
        entries = []
        try:
            for child in sorted(
                path.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower())
            ):
                if child.name.startswith("."):
                    continue
                if child.is_dir():
                    entries.append({"name": child.name, "is_dir": True})
                elif not ext or child.name.endswith(ext):
                    entries.append({"name": child.name, "is_dir": False})
        except OSError:
            pass
        with self.app.state as state:
            state.fx_dir = str(path)
            state.fx_entries = entries

    def on_up(self):
        self._list_dir(Path(self.app.state.fx_dir).parent)

    def on_entry(self, name: str, is_dir: bool):
        current = Path(self.app.state.fx_dir)
        if is_dir:
            self._list_dir(current / name)
            return
        if self.app.state.fx_mode == "save":
            with self.app.state as state:
                state.fx_filename = name
            return
        target = current / name
        try:
            head = target.read_text(errors="replace")[:PREVIEW_BYTES]
        except OSError:
            head = "(unreadable)"
        with self.app.state as state:
            state.fx_preview = head
            state.fx_filename = name

    def on_confirm(self):
        state = self.app.state
        name = state.fx_filename
        if not name:
            return
        if (
            state.fx_mode == "save"
            and state.fx_filter
            and not name.endswith(state.fx_filter)
        ):
            name += state.fx_filter
        target = Path(state.fx_dir) / name
        with self.app.state as s:
            s.fx_open = False
        if self._callback:
            self._callback(target)

    def on_cancel(self):
        with self.app.state as state:
            state.fx_open = False

    # -- ui ---------------------------------------------------------------------
    def build(self):
        with v3.VDialog(v_model=("fx_open",), max_width=720):
            with v3.VCard(classes="file-explorer"):
                v3.VCardTitle("{{ fx_title }}")
                with v3.VCardText(style="max-height: 420px; overflow-y: auto;"):
                    with html.Div(classes="d-flex align-center mb-2"):
                        v3.VBtn(
                            icon="mdi-arrow-up",
                            size="small",
                            variant="text",
                            classes="fx-up",
                            click=self.on_up,
                        )
                        html.Span("{{ fx_dir }}", classes="text-caption ml-2 fx-path")
                    with v3.VList(density="compact", classes="fx-list"):
                        with v3.VListItem(
                            v_for="entry in fx_entries",
                            key="entry.name",
                            classes="fx-entry",
                            click=(
                                self.on_entry,
                                "[entry.name, entry.is_dir]",
                            ),
                        ):
                            with html.Template(v_slot_prepend=True):
                                v3.VIcon(
                                    "{{ entry.is_dir ? 'mdi-folder' : 'mdi-file-outline' }}",
                                    size="small",
                                )
                            v3.VListItemTitle("{{ entry.name }}")
                    html.Pre(
                        "{{ fx_preview }}",
                        v_show="fx_preview",
                        classes="fx-preview text-caption",
                        style=(
                            "max-height: 120px; overflow: auto;"
                            "background: #f5f5f5; padding: 4px;"
                        ),
                    )
                with v3.VCardActions():
                    v3.VTextField(
                        v_model=("fx_filename",),
                        label="File name",
                        density="compact",
                        hide_details=True,
                        classes="fx-filename",
                    )
                    v3.VSpacer()
                    v3.VBtn("Cancel", classes="fx-cancel", click=self.on_cancel)
                    v3.VBtn(
                        "{{ fx_mode === 'save' ? 'Save' : 'Open' }}",
                        color="primary",
                        classes="fx-confirm",
                        click=self.on_confirm,
                    )
