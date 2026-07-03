/* celeri-deck: interactive deck.gl map component for trame (Vue 3, no build).
 *
 * Renders JSON layer descriptors and forwards deck.gl interaction events
 * (click / hover / drag / view-state / keys) to the trame server. Dragging is
 * client-side: a "ghost" override moves the picked point locally at 60 fps and
 * the server commits once on dragend.
 *
 * Layer descriptor format (plain JSON, produced by celeri_builder.deck):
 *   { "type": "ScatterplotLayer", "id": "vertices", "data": [...rows...],
 *     "getPosition": ["@lon", "@lat"], "getFillColor": [30, 30, 30, 255],
 *     "radiusMinPixels": 4, ... }
 * Accessor rule: any prop whose name starts with "get" and whose value is
 * "@field" (or an array of "@field" strings) becomes a row accessor; anything
 * else passes through as a constant.
 *
 * Antimeridian twins: layers whose id ends in "__shift" are the -360deg
 * duplicates of their base layer; events report the base id.
 */

(function () {
  "use strict";

  const SHIFT_SUFFIX = "__shift";

  function baseLayerId(id) {
    return id.endsWith(SHIFT_SUFFIX) ? id.slice(0, -SHIFT_SUFFIX.length) : id;
  }

  function makeAccessor(value) {
    if (typeof value === "string" && value.startsWith("@")) {
      const field = value.slice(1);
      return (d) => d[field];
    }
    if (
      Array.isArray(value) &&
      value.length > 0 &&
      value.every((v) => typeof v === "string" && v.startsWith("@"))
    ) {
      const fields = value.map((v) => v.slice(1));
      return (d) => fields.map((f) => d[f]);
    }
    return value;
  }

  const CeleriDeckComponent = {
    name: "CeleriDeck",
    props: {
      layers: { type: Array, default: () => [] },
      mapStyle: { default: null },
      viewState: {
        type: Object,
        default: () => ({ longitude: 0, latitude: 0, zoom: 2 }),
      },
      viewStateRevision: { type: Number, default: 0 },
      dragLayers: { type: Array, default: () => [] },
      cursorMode: { type: String, default: "auto" },
      hoverRateMs: { type: Number, default: 100 },
      dragRateMs: { type: Number, default: 66 },
      viewstateRateMs: { type: Number, default: 200 },
    },
    emits: [
      "ready",
      "click",
      "hover",
      "dragstart",
      "drag",
      "dragend",
      "viewstate",
      "mapkey",
    ],
    created() {
      // Non-reactive internals
      this._deck = null;
      this._ghost = null;
      this._ghostRev = 0;
      this._dragging = false;
      this._dragInfo = null;
      this._armed = false;
      this._lastHover = 0;
      this._lastDrag = 0;
      this._vsTimer = null;
      this._raf = null;
      this._keyHandler = null;
    },
    mounted() {
      const opts = {
        container: this.$el,
        initialViewState: { ...this.viewState },
        controller: true,
        layers: this._buildLayers(),
        onClick: (info, event) => this._onClick(info, event),
        onHover: (info) => this._onHover(info),
        onDragStart: (info, event) => this._onDragStart(info, event),
        onDrag: (info) => this._onDrag(info),
        onDragEnd: (info) => this._onDragEnd(info),
        onViewStateChange: ({ viewState }) => this._onViewStateChange(viewState),
        getCursor: ({ isDragging, isHovering }) =>
          this._getCursor(isDragging, isHovering),
        getTooltip: (info) =>
          info && info.object && info.object.tooltip
            ? { html: info.object.tooltip }
            : null,
      };
      if (this.mapStyle) {
        opts.map = window.maplibregl;
        opts.mapStyle = this.mapStyle;
      }
      this._deck = new window.deck.DeckGL(opts);
      this._keyHandler = (e) => this._onKey(e);
      window.addEventListener("keydown", this._keyHandler);
      this.$emit("ready", {});
    },
    beforeUnmount() {
      if (this._keyHandler) window.removeEventListener("keydown", this._keyHandler);
      if (this._raf) cancelAnimationFrame(this._raf);
      if (this._vsTimer) clearTimeout(this._vsTimer);
      if (this._deck) this._deck.finalize();
      this._deck = null;
    },
    watch: {
      layers(newVal, oldVal) {
        // The bound expression concatenates per-group arrays, so it yields a
        // new outer array on every template re-render; only element identity
        // tells us whether the server actually pushed new layer data.
        if (
          oldVal &&
          newVal &&
          newVal.length === oldVal.length &&
          newVal.every((l, i) => l === oldVal[i])
        ) {
          return;
        }
        // Fresh data from the server supersedes any local ghost.
        this._ghost = null;
        this._redraw();
      },
      viewStateRevision() {
        if (this._deck) {
          this._deck.setProps({ initialViewState: { ...this.viewState } });
        }
      },
      mapStyle(value) {
        if (this._deck) this._deck.setProps({ mapStyle: value || null });
      },
    },
    methods: {
      _payload(info, event) {
        const src = (event && event.srcEvent) || {};
        const picked = Boolean(info && info.picked && info.layer);
        return {
          coordinate: (info && info.coordinate) || null,
          picked,
          layerId: picked ? baseLayerId(info.layer.id) : null,
          index: picked && info.index !== undefined ? info.index : -1,
          x: info ? info.x : null,
          y: info ? info.y : null,
          shiftKey: !!src.shiftKey,
          ctrlKey: !!src.ctrlKey,
          altKey: !!src.altKey,
          metaKey: !!src.metaKey,
        };
      },
      _onClick(info, event) {
        this.$emit("click", this._payload(info, event));
      },
      _onHover(info) {
        if (this._dragging || !this._deck) return;
        const overDraggable = Boolean(
          info &&
            info.picked &&
            info.layer &&
            info.index >= 0 &&
            this.dragLayers.includes(baseLayerId(info.layer.id)),
        );
        if (overDraggable !== this._armed) {
          this._armed = overDraggable;
          this._deck.setProps({
            controller: overDraggable
              ? { dragPan: false, dragRotate: false }
              : true,
          });
        }
        const now = Date.now();
        if (now - this._lastHover >= this.hoverRateMs) {
          this._lastHover = now;
          this.$emit("hover", this._payload(info, null));
        }
      },
      _onDragStart(info, event) {
        const draggable = Boolean(
          info &&
            info.picked &&
            info.layer &&
            info.index >= 0 &&
            this.dragLayers.includes(baseLayerId(info.layer.id)),
        );
        if (!draggable || !info.coordinate) return;
        this._dragging = true;
        this._dragInfo = {
          layerId: baseLayerId(info.layer.id),
          index: info.index,
          start: info.coordinate.slice(),
        };
        this._ghost = {
          layerId: this._dragInfo.layerId,
          index: info.index,
          coordinate: info.coordinate.slice(),
        };
        if (event && event.stopPropagation) event.stopPropagation();
        this.$emit("dragstart", {
          coordinate: info.coordinate,
          layerId: this._dragInfo.layerId,
          index: this._dragInfo.index,
        });
      },
      _onDrag(info) {
        if (!this._dragging || !this._ghost || !info || !info.coordinate) return;
        this._ghost.coordinate = info.coordinate.slice();
        this._scheduleRedraw();
        const now = Date.now();
        if (now - this._lastDrag >= this.dragRateMs) {
          this._lastDrag = now;
          this.$emit("drag", {
            coordinate: info.coordinate,
            layerId: this._dragInfo.layerId,
            index: this._dragInfo.index,
          });
        }
      },
      _onDragEnd(info) {
        if (!this._dragging) return;
        this._dragging = false;
        this._armed = false;
        this._deck.setProps({ controller: true });
        const coordinate =
          (info && info.coordinate) || this._ghost.coordinate || null;
        this.$emit("dragend", {
          coordinate,
          startCoordinate: this._dragInfo.start,
          layerId: this._dragInfo.layerId,
          index: this._dragInfo.index,
        });
        // Ghost intentionally persists until the layers prop changes so the
        // point does not snap back while the server rebuild is in flight.
      },
      _onViewStateChange(viewState) {
        if (this._vsTimer) clearTimeout(this._vsTimer);
        this._vsTimer = setTimeout(() => {
          this.$emit("viewstate", {
            longitude: viewState.longitude,
            latitude: viewState.latitude,
            zoom: viewState.zoom,
            pitch: viewState.pitch || 0,
            bearing: viewState.bearing || 0,
          });
        }, this.viewstateRateMs);
      },
      _onKey(e) {
        const t = e.target;
        if (
          t &&
          (t.tagName === "INPUT" ||
            t.tagName === "TEXTAREA" ||
            t.tagName === "SELECT" ||
            t.isContentEditable)
        ) {
          return;
        }
        if (e.key === "Enter" || e.key === "Escape") {
          this.$emit("mapkey", { key: e.key });
        }
      },
      _getCursor(isDragging, isHovering) {
        if (this.cursorMode === "crosshair") return "crosshair";
        if (this._dragging) return "grabbing";
        if (this._armed) return "move";
        if (isHovering) return "pointer";
        return isDragging ? "grabbing" : "grab";
      },
      _scheduleRedraw() {
        if (this._raf) return;
        this._raf = requestAnimationFrame(() => {
          this._raf = null;
          this._redraw();
        });
      },
      _redraw() {
        if (!this._deck) return;
        this._ghostRev += 1;
        this._deck.setProps({ layers: this._buildLayers() });
      },
      _buildLayers() {
        const ghost = this._ghost;
        const ghostRev = this._ghostRev;
        const out = [];
        for (const desc of this.layers || []) {
          const { type, id, data, updateTriggers, ...rest } = desc;
          const LayerClass = window.deck[type];
          if (!LayerClass) {
            console.warn("celeri-deck: unknown layer type", type);
            continue;
          }
          const props = { id, data };
          for (const [key, value] of Object.entries(rest)) {
            props[key] = key.startsWith("get") ? makeAccessor(value) : value;
          }
          if (updateTriggers) props.updateTriggers = updateTriggers;
          if (
            ghost &&
            (id === ghost.layerId || id === ghost.layerId + SHIFT_SUFFIX)
          ) {
            const shift = id.endsWith(SHIFT_SUFFIX) ? -360 : 0;
            const gcoord = [ghost.coordinate[0] + shift, ghost.coordinate[1]];
            const base = props.getPosition;
            props.getPosition = (d, ctx) =>
              ctx && ctx.index === ghost.index
                ? gcoord
                : typeof base === "function"
                  ? base(d, ctx)
                  : base;
            props.updateTriggers = {
              ...(props.updateTriggers || {}),
              getPosition: [ghostRev],
            };
          }
          out.push(new LayerClass(props));
        }
        return out;
      },
    },
    template:
      '<div class="celeri-deck" style="position: relative; width: 100%; height: 100%; overflow: hidden;"></div>',
  };

  window.CeleriDeck = {
    install(app) {
      app.component("CeleriDeck", CeleriDeckComponent);
    },
  };
})();
