/* Keshiki background layers: crossfades between looks Python computes.
   A look is {layers: [{src, opacity, x, y, grade?, light?, lights?, glow?}],
   dim: 0-1, blur: px, fade: ms}, layers bottom first. A grade is [[gain r, g, b],
   [offset r, g, b]] in sRGB (smoothing a fade); light is the daylight matrix
   in linear RGB (daylight.py); lights is the picture's lights alone (library.py),
   glow (0-1) how much they shine through at night and bloom (0-1) how much
   they glow around. No build step. */
(function () {
  if (window.keshiki) return;

  function div(cls) {
    const el = document.createElement("div");
    el.className = cls;
    return el;
  }

  const SVG = "http://www.w3.org/2000/svg";
  const SMALL_STEP_MS = 800;
  let filterCount = 0;

  function node(tag, attrs) {
    const el = document.createElementNS(SVG, tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    return el;
  }

  // Resolves when an opacity transition on el ends (or soon after it should have).
  function faded(el, ms) {
    return new Promise((resolve) => {
      const timer = setTimeout(done, ms + 100);
      function done() {
        clearTimeout(timer);
        el.removeEventListener("transitionend", onEnd);
        resolve();
      }
      function onEnd(e) {
        if (e.target === el && e.propertyName === "opacity") done();
      }
      el.addEventListener("transitionend", onEnd);
    });
  }

  function loaded(src) {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = img.onerror = () => resolve();
      img.src = src;
    });
  }

  class Stage {
    constructor(host, fixed) {
      this.root = div("keshiki-stage" + (fixed ? " keshiki-fixed" : ""));
      this.root.setAttribute("aria-hidden", "true");
      this.stack = div("keshiki-stack");
      this.dim = div("keshiki-dim");
      // Holds each graded layer's colour-matrix filter.
      this.filters = document.createElementNS(SVG, "svg");
      this.filters.setAttribute("width", "0");
      this.filters.setAttribute("height", "0");
      this.filters.style.position = "absolute";
      this.root.append(this.filters, this.stack, this.dim);
      this.root.style.opacity = "0";
      host.appendChild(this.root);
      this.fixed = fixed;
      this.shown = null;
      this.onEmpty = null;
    }

    // Window size and this webview's offset in it, in CSS px.
    geom(g) {
      Object.assign(this.root.style, {
        left: -g.x + "px", top: -g.y + "px", width: g.w + "px", height: g.h + "px",
        right: "auto", bottom: "auto",
      });
    }

    apply(look, instant) {
      const key = JSON.stringify(look || null);
      if (key === this.shown) return;
      this.shown = key;
      // Each look is a step; work a step defers (dropping covered layers) is skipped
      // once a newer one has taken over the stack, which may have kept those layers.
      const step = (this.step = (this.step || 0) + 1);
      // A small step (the same pictures, every value moving under 3%) gets a short ease
      // instead of the full one: smooth to the eye, and the filtered pictures are redrawn
      // for well under a second instead of the whole crossfade.
      const small = look && this.small(this.last, look);
      this.last = look;
      const ms = instant ? 0 : small ? Math.min(SMALL_STEP_MS, (look && look.fade) || 0) : (look && look.fade) || 0;
      this.root.style.setProperty("--kk-fade", ms + "ms");
      const want = (look && look.layers) || [];
      if (!want.length) {
        this.root.style.opacity = "0";
        if (this.onEmpty) setTimeout(() => this.shown === key && this.onEmpty(), ms);
        return;
      }
      if (this.onShow) this.onShow();
      this.root.style.opacity = "1";
      this.dim.style.opacity = String(look.dim || 0);
      const blur = look.blur || 0;
      this.stack.style.filter = blur ? `blur(${blur}px)` : "";
      // Overscan when blurred so the window's edges don't fade to transparent.
      this.stack.style.inset = -2 * blur + "px";

      const live = [...this.stack.children].filter((el) => !el.dataset.leaving);
      // Carry on with the newest layer already showing the base picture, wherever it is
      // in the stack (just after a change, the old picture is still underneath it).
      const at = live.map((el) => el.dataset.src).lastIndexOf(want[0].src);
      if (at >= 0) {
        const base = live[at];
        const was = base.target;
        this.set(base, want[0]);
        // A top layer becoming the base is painted once it has faded the rest of the way in.
        if (!base.loading && was < want[0].opacity) base.ready = base.ready.then(() => faded(base, ms));
        // What's under it goes once it's painted: the base is opaque, so nothing shows through.
        for (const el of live.slice(0, at)) {
          el.dataset.leaving = "1";
          base.ready.then(() => this.leave(el, ms, true));
        }
        const above = live.slice(at + 1);
        const top = want[1];
        const liveTop = top && above.find((el) => el.dataset.src === top.src);
        if (liveTop) this.set(liveTop, top);
        else if (top) this.enter(top, ms);
        for (const el of above) if (el !== liveTop) this.leaveOver(base, el, ms);
        return;
      }
      // A different picture: lay it over the old one, then drop the old one once it's covered.
      const entering = want.map((layer) => this.enter(layer, ms));
      Promise.all(entering).then(() => {
        if (this.step === step) for (const el of live) this.leave(el, ms, true);
      });
    }

    // Fading out a layer while the one beneath is still fading in would let the
    // background show through both (a dark flash at each change in a timelapse), so
    // it waits for the base to be painted. It's out of the live set at once.
    leaveOver(base, el, ms) {
      el.dataset.leaving = "1";
      (base.ready || Promise.resolve()).then(() => this.leave(el, ms));
    }

    small(prev, look) {
      if (!prev || !prev.layers || prev.layers.length !== look.layers.length) return false;
      if (prev.dim !== look.dim || prev.blur !== look.blur) return false;
      const near = (a, b) => Math.abs((a || 0) - (b || 0)) <= 0.03;
      const nearAll = (a, b) => (!a && !b) || (a && b && a.flat(Infinity).every((x, i) => near(x, b.flat(Infinity)[i])));
      return look.layers.every((l, i) => {
        const p = prev.layers[i];
        return p.src === l.src && p.lights === l.lights && near(p.opacity, l.opacity) && near(p.glow, l.glow)
          && near(p.bloom, l.bloom) && nearAll(p.light, l.light) && nearAll(p.grade, l.grade);
      });
    }

    // A layer is a group: the picture (with its fade grade and daylight), and, at
    // night, its own lights on top, kept out of the daylight, brightened a little and
    // softly blooming. Opacity on the group crossfades all of it together.
    set(el, layer) {
      el.style.setProperty("--kx", layer.x + "%");
      el.style.setProperty("--ky", layer.y + "%");
      el.target = layer.opacity;
      if (!el.loading) el.style.opacity = String(layer.opacity);
      this.filter(el.pic, layer);
      const glow = layer.lights ? layer.glow || 0 : 0;
      for (const part of [el.lights, el.bloom]) {
        if (glow && part.dataset.src !== layer.lights) {
          part.style.backgroundImage = `url("${layer.lights}")`;
          part.dataset.src = layer.lights;
        }
      }
      el.lights.style.opacity = String(glow);
      el.lights.style.filter = `brightness(${1 + 0.35 * glow})`;
      // The bloom's spread follows the size of what it's drawn on.
      const spread = Math.max(3, Math.round((this.root.clientWidth || 1200) * 0.009));
      // bloom 0.5 is the standard look; 1 doubles it, 0 turns it off.
      const bloom = layer.bloom ?? 0.5;
      el.bloom.style.opacity = String(Math.min(1, 2 * bloom * glow));
      el.bloom.style.filter = `blur(${spread}px) brightness(3)`;
    }

    // The picture's filter: grade (sRGB, smoothing a fade) then daylight (linear light).
    filter(pic, layer) {
      if (!layer.grade && !layer.light) {
        pic.style.filter = "";
        return;
      }
      if (!pic.fx) {
        const id = "keshiki-light-" + ++filterCount;
        const f = node("filter", { id });
        pic.fx = {
          grade: node("feColorMatrix", { type: "matrix", in: "SourceGraphic", "color-interpolation-filters": "sRGB" }),
          light: node("feColorMatrix", { type: "matrix" }),
        };
        f.append(pic.fx.grade, pic.fx.light);
        this.filters.append(f);
        pic.filterId = id;
      }
      const g = layer.grade || [[1, 1, 1], [0, 0, 0]];
      pic.fx.grade.setAttribute("values",
        `${g[0][0]} 0 0 0 ${g[1][0]}  0 ${g[0][1]} 0 0 ${g[1][1]}  0 0 ${g[0][2]} 0 ${g[1][2]}  0 0 0 1 0`);
      const [r, gr, b] = layer.light || [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
      pic.fx.light.setAttribute("values", `${r.join(" ")} 0 0  ${gr.join(" ")} 0 0  ${b.join(" ")} 0 0  0 0 0 1 0`);
      pic.style.filter = `url(#${pic.filterId})`;
    }

    enter(layer, ms) {
      const el = div("keshiki-layer");
      el.dataset.src = layer.src;
      el.pic = div("keshiki-pic");
      el.pic.style.backgroundImage = `url("${layer.src}")`;  // Python URL-quotes src
      el.lights = div("keshiki-lights");
      el.bloom = div("keshiki-bloom");
      el.append(el.pic, el.lights, el.bloom);
      el.loading = !!ms;
      this.set(el, layer);
      el.style.opacity = ms ? "0" : String(layer.opacity);
      this.stack.appendChild(el);
      if (!ms) return (el.ready = Promise.resolve());
      // Fade in only once the image can paint, or it fades in from nothing; to the
      // latest opacity, which a step since may have changed.
      el.ready = loaded(layer.src).then(() => {
        el.loading = false;
        if (el.dataset.leaving) return;   // on its way out before it could paint
        void el.offsetWidth;
        el.style.opacity = String(el.target);
        return faded(el, ms);
      });
      return el.ready;
    }

    leave(el, ms, underneath) {
      el.dataset.leaving = "1";
      // Something already covers a layer that's underneath; it can just go.
      if (!underneath) el.style.opacity = "0";
      setTimeout(() => {
        el.remove();
        if (el.pic.filterId) document.getElementById(el.pic.filterId)?.remove();
      }, underneath ? 0 : ms);
    }
  }

  // Card templates that paint their own page background (a themed full-width
  // wrapper, as in Kiku's DaisyUI themes) would cover the picture down to where
  // their content ends. While a background shows, full-width wrappers are made
  // see-through; narrower panels (the card itself) keep theirs, so text stays readable.
  const backdrops = {
    cleared: new Map(),   // element -> its own inline background-color and priority, to put back
    observed: new WeakSet(),
    queued: false,

    opaque(el) {
      const style = getComputedStyle(el);
      const rgba = style.backgroundColor.match(/[\d.]+/g) || [];
      const alpha = rgba.length < 4 ? (rgba.length ? 1 : 0) : Number(rgba[3]);
      return alpha >= 0.3 && style.backgroundImage === "none";
    },

    // Look down from the page through wide elements only: once something is
    // narrower than the window it's a panel, and everything inside it is left alone.
    visit(root, depth) {
      for (const el of root.children) {
        if (el.classList.contains("keshiki-stage")) continue;
        // A web component can report no size of its own while its content fills the
        // page, so look inside those whatever their width.
        if (el.shadowRoot && depth < 8) {
          this.watch(el.shadowRoot);
          this.visit(el.shadowRoot, depth + 1);
        }
        const wide = el.getBoundingClientRect().width >= window.innerWidth * 0.9;
        if (!wide && !el.tagName.includes("-")) continue;
        if (wide && this.opaque(el)) {
          if (!this.cleared.has(el)) {
            this.cleared.set(el, [el.style.getPropertyValue("background-color"), el.style.getPropertyPriority("background-color")]);
          }
          el.style.setProperty("background-color", "transparent", "important");
        }
        if (depth < 8) this.visit(el, depth + 1);
      }
    },

    run() {
      this.queued = false;
      if (document.body && document.documentElement.classList.contains("keshiki-on")) {
        // Card styles arrive with each card, after the page loads: check both again.
        this.scrollbar(true);
        this.visit(document.body, 0);
      }
    },

    soon() {
      if (!this.queued) {
        this.queued = true;
        requestAnimationFrame(() => this.run());
      }
    },

    watch(root) {
      if (this.observed.has(root)) return;
      this.observed.add(root);
      // Attributes too: templates often reveal themselves by dropping a "cloak" attribute or class.
      new MutationObserver(() => this.soon()).observe(root, { childList: true, attributes: true, subtree: true });
    },

    scrollbar(on) {
      if (!document.body) return document.addEventListener("DOMContentLoaded", () => this.scrollbar(on), { once: true });
      // Only a scrollbar forced on (overflow-y: scroll); the toolbars hide theirs on purpose.
      for (const el of [document.documentElement, document.body]) {
        if (on && getComputedStyle(el).overflowY === "scroll") {
          el.style.setProperty("overflow-y", "auto", "important");
          el.dataset.keshikiScroll = "1";
        } else if (!on && el.dataset.keshikiScroll) {
          el.style.removeProperty("overflow-y");
          delete el.dataset.keshikiScroll;
        }
      }
    },

    restore() {
      for (const [el, [value, priority]] of this.cleared) {
        if (value) el.style.setProperty("background-color", value, priority);
        else el.style.removeProperty("background-color");
      }
      this.cleared.clear();
    },
  };

  window.keshiki = {
    Stage,
    main: null,
    backdrops,
    // The main window's stage, behind everything on the page.
    mount(geom, look) {
      if (!this.main) {
        const html = document.documentElement;
        const stage = (this.main = new Stage(html, true));
        stage.onShow = () => {
          html.classList.add("keshiki-on");
          // The picture can't reach under the page's scrollbar, so a template that forces one
          // on every card (Kiku) leaves a strip of its own colour there. Show it only when the
          // card needs scrolling, as Anki does. Inline !important outranks the template's rules.
          backdrops.scrollbar(true);
          backdrops.soon();
        };
        stage.onEmpty = () => {
          html.classList.remove("keshiki-on");
          backdrops.scrollbar(false);
          backdrops.restore();
        };
        const start = () => {
          backdrops.watch(document.body);
          backdrops.soon();
        };
        if (document.body) start();
        else document.addEventListener("DOMContentLoaded", start);
        // Zooming the page (Ctrl+wheel, View > Zoom) changes the window's size in its CSS
        // pixels without resizing any widget, so ask Python for the geometry again.
        let asked = false;
        window.addEventListener("resize", () => {
          backdrops.soon();
          if (asked || typeof pycmd !== "function") return;
          asked = true;
          requestAnimationFrame(() => { asked = false; pycmd("keshiki:geometry"); });
        });
      }
      this.main.geom(geom);
      this.main.apply(look, true);
    },
  };
})();
