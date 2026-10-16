/* Keshiki background layers: crossfades between looks Python computes.
   A look is {layers: [{src, opacity, x, y, grade?, light?, lights?, glow?}],
   dim: 0-1, blur: px, fade: ms}, layers bottom first. A grade is [[gain r, g, b],
   [offset r, g, b]] in sRGB (smoothing a fade); light is the daylight matrix
   in linear RGB (daylight.py); lights is the picture's lights alone (library.py),
   glow (0-1) how much they shine through at night and bloom (0-1) how much
   they glow around. backdrops: the deck list's, on screens that use them (see backdrop
   and contrast below). No build step. */
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

  // Resolves once the page has drawn a frame with what's there now.
  function drawn() {
    return new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  }

  function loaded(src) {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = img.onerror = () => resolve();
      img.src = src;
    });
  }

  // A faint static grain over the stage: mid grey at an alpha of 0-6 (of 255) per pixel, so
  // each pixel is moved by a level or two at most, differently from its neighbours. A slow
  // fade between close colours (a dark picture dimming toward a dark theme) has only a few
  // levels to pass through, and without it whole regions step together, visibly; with it,
  // neighbours step at different moments and the fade reads as continuous (dithering).
  let grainUrl = null;
  function grain() {
    if (!grainUrl) {
      const size = 256;
      const canvas = Object.assign(document.createElement("canvas"), { width: size, height: size });
      const ctx = canvas.getContext("2d");
      const img = ctx.createImageData(size, size);
      for (let i = 0; i < img.data.length; i += 4) {
        img.data[i] = img.data[i + 1] = img.data[i + 2] = 128;
        img.data[i + 3] = Math.floor(Math.random() * 7);
      }
      ctx.putImageData(img, 0, 0);
      grainUrl = canvas.toDataURL("image/png");
    }
    return grainUrl;
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
      this.grain = div("keshiki-grain");
      this.grain.style.backgroundImage = `url("${grain()}")`;
      this.root.append(this.filters, this.stack, this.dim, this.grain);
      this.root.style.opacity = "0";
      host.appendChild(this.root);
      this.fixed = fixed;
      this.shown = null;
      this.onEmpty = null;
      // Fades need a frame drawn first, or a page still loading jumps to the end.
      this.drawn = false;
      drawn().then(() => { this.drawn = true; });
    }

    // Window size and this webview's offset in it, in CSS px.
    geom(g) {
      Object.assign(this.root.style, {
        left: -g.x + "px", top: -g.y + "px", width: g.w + "px", height: g.h + "px",
        right: "auto", bottom: "auto",
      });
    }

    // A crossfade that began elsewhere at `began` (ms since the epoch): the bars have been
    // fading since, and so had the page this one replaces. This page starts where they are:
    // its very first frame is already that far into the fade, on the same curve, and it ends
    // with them. Web Animations do that (a CSS transition can't start before a frame is drawn,
    // so the page would show the look before for a moment: a flicker back, then forward).
    join(look, began) {
      const total = (look && look.fade) || 0, gone = Math.max(0, Date.now() - began);
      const layers = (look && look.layers) || [];
      if (!layers.length || gone >= total - 30) return this.apply(look, true);
      const timing = { duration: total, delay: -gone, easing: "ease-in-out", fill: "backwards" };
      const d0 = Number(this.dim.style.opacity || 0);
      const old = [...this.stack.children];
      this.shown = JSON.stringify(look);
      this.last = look;
      this.blur = look.blur || 0;
      // The animations below do the fading; CSS transitions stay out of it.
      this.root.style.setProperty("--kk-fade", "0ms");
      this.root.style.setProperty("--kk-delay", "0ms");
      if (this.onLook) this.onLook(look);
      if (this.onShow) this.onShow();
      this.root.style.opacity = "1";
      this.dim.style.opacity = String(look.dim || 0);
      this.dim.animate([{ opacity: d0 }, { opacity: look.dim || 0 }], timing);
      const keys = layers.map((l) => `${l.src}@${this.blur}`);
      if (keys.join(" ") === old.map((el) => el.dataset.key).join(" ")) {
        old.forEach((el, i) => this.set(el, layers[i]));   // the same pictures: only the dim changes
        return;
      }
      // New pictures (or a new blur) fade in over the old, which go once they're covered.
      for (const layer of layers) {
        this.enter(layer, 0);
        this.stack.lastElementChild.animate([{ opacity: 0 }, { opacity: layer.opacity }], timing);
      }
      for (const el of old) {
        el.dataset.leaving = "1";
        setTimeout(() => this.leave(el, 0, true), total - gone + 50);
      }
    }

    // `gone` (ms): how long ago this change began elsewhere; its transitions start that far
    // into their curve (a negative transition delay), so they end with the others.
    apply(look, instant, gone = 0) {
      // A fade on a page that hasn't drawn yet waits for its first frame: dim, blur and
      // pictures all fade, instead of jumping to the end. A look asked for meanwhile wins:
      // the waiting one is dropped, not laid over it.
      const asked = (this.asked = (this.asked || 0) + 1);
      if (!instant && !this.drawn) {
        drawn().then(() => {
          this.drawn = true;
          if (this.asked === asked) this.apply(look, false, gone);
        });
        return;
      }
      const key = JSON.stringify(look || null);
      if (key === this.shown) return;
      this.shown = key;
      if (this.onLook) this.onLook(look);
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
      this.root.style.setProperty("--kk-delay", ms && gone > 0 ? -gone + "ms" : "0ms");
      this.began = ms && gone > 0 ? Date.now() - gone : null;   // for pictures that start fading later
      const want = (look && look.layers) || [];
      if (!want.length) {
        this.root.style.opacity = "0";
        if (this.onEmpty) setTimeout(() => this.shown === key && this.onEmpty(), ms);
        return;
      }
      if (this.onShow) this.onShow();
      this.root.style.opacity = "1";
      this.dim.style.opacity = String(look.dim || 0);
      // Blur belongs to each layer and is never animated (re-blurring the window every frame
      // halves the frame rate): a change of blur crossfades to layers drawn at the new blur,
      // as a change of picture does. A layer is its picture at its blur.
      this.blur = look.blur || 0;
      const layerKey = (layer) => `${layer.src}@${this.blur}`;

      const live = [...this.stack.children].filter((el) => !el.dataset.leaving);
      // Carry on with the newest layer already showing the base picture, wherever it is
      // in the stack (just after a change, the old picture is still underneath it).
      const at = live.map((el) => el.dataset.key).lastIndexOf(layerKey(want[0]));
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
        const liveTop = top && above.find((el) => el.dataset.key === layerKey(top));
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
      el.dataset.key = `${layer.src}@${this.blur || 0}`;
      if (this.blur) {
        el.style.filter = `blur(${this.blur}px)`;
        el.style.inset = -2 * this.blur + "px";   // overscan, so the window's edges don't fade out
      }
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
      // latest opacity, which a step since may have changed. (A page that hasn't drawn a
      // frame yet never gets here: apply waits for one.)
      const began = this.began;
      el.ready = loaded(layer.src).then(() => {
        el.loading = false;
        if (el.dataset.leaving) return;   // on its way out before it could paint
        void el.offsetWidth;
        // A change being caught up (see apply): as far into the fade as it is by now.
        if (began) el.style.transitionDelay = Math.min(0, began - Date.now()) + "ms";
        el.style.opacity = String(el.target);
        return faded(el, ms).then(() => { el.style.transitionDelay = ""; });
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

  // The deck list's backdrops, on screens that use them (look.backdrops). The deck table has a
  // see-through panel of its own: it takes their opacity and frost (a blur of the picture
  // behind it). What other add-ons show under it (Review Heatmap, Study Time Stats) and the
  // "Studied N cards" line sit right on the picture, where text is hard to read: they get a
  // panel in the table's style, fitted to their text and graphics (not the full-width boxes
  // they're in) and following them as the page changes.
  const backdrop = {
    el: null,
    settings: null,
    queued: false,

    set(look) {
      this.settings = look && look.layers && look.layers.length ? look.backdrops || null : null;
      this.soon();
    },

    soon() {
      if (!this.queued) {
        this.queued = true;
        requestAnimationFrame(() => this.place());
      }
    },

    // What comes after the deck table: its later siblings, then anything after its <center>.
    content() {
      const table = document.querySelector("center > table");
      if (!table || !table.querySelector("tr.deck")) return [];
      const after = (el) => {
        const out = [];
        for (let n = el.nextSibling; n; n = n.nextSibling) out.push(n);
        return out;
      };
      return [...after(table), ...after(table.parentElement)];
    },

    // Tight rectangles of what's drawn: text runs, pictures and painted boxes narrower
    // than the window. A wide wrapper is looked into, not counted.
    rects(nodes, out) {
      for (const node of nodes) {
        if (node.nodeType === Node.TEXT_NODE) {
          if (!node.textContent.trim()) continue;
          const range = document.createRange();
          range.selectNodeContents(node);
          out.push(...range.getClientRects());
          continue;
        }
        if (node.nodeType !== Node.ELEMENT_NODE || node === this.el || node.classList.contains("keshiki-stage")
            || /^(SCRIPT|STYLE|TEMPLATE|BR)$/.test(node.tagName)) continue;
        const style = getComputedStyle(node);
        if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) continue;
        const r = node.getBoundingClientRect();
        const narrow = r.width > 0 && r.height > 0 && r.width < window.innerWidth * 0.9;
        const graphic = /^(IMG|SVG|CANVAS|VIDEO|BUTTON|INPUT|SELECT)$/i.test(node.tagName)
          || (!node.children.length && !node.textContent.trim());
        const painted = !/^rgba\(0, 0, 0, 0\)$|transparent/.test(style.backgroundColor)
          || style.backgroundImage !== "none" || parseFloat(style.borderTopWidth) > 0;
        if (narrow && (graphic || painted)) out.push(r);
        else this.rects(node.childNodes, out);
      }
      return out;
    },

    place() {
      this.queued = false;
      if (!document.body) return;
      const html = document.documentElement;
      const s = this.settings;
      const decks = !!s && html.classList.contains("keshiki-on") && !!document.querySelector("center > table tr.deck");
      const table = (s && s.table) || {}, panel = (s && s.panel) || {};
      const vars = {
        "--kk-table": (table.opacity ?? 40) + "%", "--kk-table-frost": (table.frost || 0) + "px",
        "--kk-panel": (panel.opacity ?? 40) + "%", "--kk-panel-frost": (panel.frost || 0) + "px",
        "--kk-panel-color": panel.color || "var(--canvas-elevated, #363636)",
      };
      html.classList.toggle("keshiki-decks", decks);
      if (decks !== this.wasDecks) {
        this.wasDecks = decks;
        if (contrast) contrast.soon(0);
      }
      if (decks) for (const [k, v] of Object.entries(vars)) if (html.style.getPropertyValue(k) !== v) html.style.setProperty(k, v);
      const rects = decks && panel.enabled ? this.rects(this.content(), []).filter((r) => r.width && r.height) : [];
      if (!rects.length) {
        if (this.el) this.el.style.display = "none";
        return;
      }
      if (!this.el) this.el = Object.assign(document.createElement("div"), { className: "keshiki-panel" });
      if (!this.el.isConnected) document.body.append(this.el);   // a redrawn page drops it
      const pad = panel.padding ?? 14;
      const left = Math.min(...rects.map((r) => r.left)), right = Math.max(...rects.map((r) => r.right));
      const top = Math.min(...rects.map((r) => r.top)), bottom = Math.max(...rects.map((r) => r.bottom));
      const style = {
        display: "block",
        left: Math.round(left + window.scrollX - pad) + "px",
        top: Math.round(top + window.scrollY - pad) + "px",
        width: Math.round(right - left + 2 * pad) + "px",
        height: Math.round(bottom - top + 2 * pad) + "px",
      };
      // Only what changed: the page's observer would otherwise hear its own writes.
      for (const [k, v] of Object.entries(style)) if (this.el.style[k] !== v) this.el.style[k] = v;
    },

    watch() {
      new MutationObserver((records) => {
        // Its own writes (the panel's place, the contrast help's styles) don't count.
        const page = records.filter((r) => r.target !== this.el && !(contrast && contrast.ours(r)));
        if (page.length) { this.soon(); if (contrast) contrast.soon(); }
      }).observe(document.body, { childList: true, subtree: true, attributes: true, characterData: true });
      window.addEventListener("resize", () => { this.soon(); if (contrast) contrast.soon(); });
    },
  };

  // Text on the picture made readable (look.backdrops.text): "needed" helps only text that's
  // hard to read, "everywhere" outlines all of it and more where needed; strength (0-100)
  // scales how much. The colour behind each text run is worked out from what Keshiki draws,
  // not a screenshot: the stage's pictures on a small canvas, cropped as the stage crops them,
  // graded, lit, crossfaded and dimmed, with the panel the text sits on laid over that. Text
  // short of 4.5:1 (WCAG's contrast ratio) is helped as much as it's short: coloured text moves
  // a little in lightness toward the theme's text (lighter in a dark theme) and a little less
  // in hue away from the colour behind it; then an outline in the text's opposite colour (dark
  // behind light text), sized to the text. Anki's zero counts are faint on purpose: left alone.
  // One Contrast per page area: Anki's deck list, or the settings page's preview of it.
  const AIM = 4.5;
  const MAX_SHIFT = 0.22;   // the most a colour's OKLCH lightness moves
  const MAX_HUE = 0.17;     // and its hue turns, in radians (about 10 degrees), in step with it

  const lin = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const unlin = (c) => (c <= 0.0031308 ? 12.92 * c : 1.055 * Math.max(c, 0) ** (1 / 2.4) - 0.055);
  const clamp = (x) => Math.min(1, Math.max(0, x));
  const luminance = (c) => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
  const ratio = (a, b) => {
    const x = luminance(a), y = luminance(b);
    return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
  };
  // "rgb(..)", "rgba(..)" or "color(srgb r g b / a)" -> [r, g, b, a], 0-1.
  function parseColor(s) {
    let m = s.match(/rgba?\(([^)]+)\)/);
    if (m) { const v = m[1].split(/[\s,/]+/).filter(Boolean).map(Number); return [v[0] / 255, v[1] / 255, v[2] / 255, v[3] ?? 1]; }
    m = s.match(/color\(srgb ([^)]+)\)/);
    if (m) { const v = m[1].split(/[\s/]+/).filter(Boolean).map(Number); return [v[0], v[1], v[2], v[3] ?? 1]; }
    return null;
  }
  // sRGB <-> OKLCH (Björn Ottosson's OKLab).
  function toOklch(c) {
    const [r, g, b] = c.map(lin);
    const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
    const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
    const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
    const A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
    const B = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
    return [0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s, Math.hypot(A, B), Math.atan2(B, A)];
  }
  function fromOklch([L, C, h]) {
    const A = C * Math.cos(h), B = C * Math.sin(h);
    const l = (L + 0.3963377774 * A + 0.2158037573 * B) ** 3;
    const m = (L - 0.1055613458 * A - 0.0638541728 * B) ** 3;
    const s = (L - 0.0894841775 * A - 1.291485548 * B) ** 3;
    return [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s].map((v) => clamp(unlin(v)));
  }
  const pictures = new Map();   // src -> Promise<Image | null>
  function picture(src) {
    if (!pictures.has(src)) {
      pictures.set(src, new Promise((resolve) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () => resolve(null);
        img.src = src;
      }));
    }
    return pictures.get(src);
  }

  class Contrast {
    // root: where the text is; stage: the Stage painting behind it; panels(): extra panels
    // that sit behind text without containing it (Keshiki's add-on panel); source(), if given,
    // the text settings as they are when it runs (instead of set()).
    constructor(root, stage, panels = () => [], source = null) {
      Object.assign(this, { root, stage, panels, source, settings: null, timer: 0, running: false, painted: null,
                            touched: new Map(), original: new WeakMap(), report: [] });
    }

    set(text) {
      this.text = text;
      this.soon(60);   // after the panels have taken the new look (their fills are part of the background)
    }

    soon(ms = 250) {
      clearTimeout(this.timer);
      this.timer = setTimeout(() => this.run(), ms);
    }

    async run() {
      if (this.running) return this.soon();   // one at a time; the latest change runs next
      this.running = true;
      try {
        const text = this.source ? this.source() : this.text;
        this.settings = text && text.outline && text.outline !== "off" ? text : null;
        if (this.settings && this.stage.shown && this.stage.shown !== "null" && this.root.isConnected) await this.adjust();
        else this.clear();
      } finally { this.running = false; }
    }

    // The area as the stage paints it, at a quarter size (kept while the look and size stay).
    async paint() {
      const SCALE = 0.25;
      const box = this.stage.root.getBoundingClientRect();
      const W = Math.max(1, Math.round(box.width * SCALE)), H = Math.max(1, Math.round(box.height * SCALE));
      const key = this.stage.shown + W + "x" + H;
      if (this.painted && this.painted.key === key) return Object.assign(this.painted, { box });
      const look = JSON.parse(this.stage.shown);
      const out = new Float32Array(W * H * 3);
      const ctx = Object.assign(document.createElement("canvas"), { width: W, height: H })
        .getContext("2d", { willReadFrequently: true });
      let first = true;
      for (const layer of look.layers || []) {
        const img = await picture(layer.src);
        if (!img) continue;
        const sc = Math.max(W / img.naturalWidth, H / img.naturalHeight);
        const dw = img.naturalWidth * sc, dh = img.naturalHeight * sc;
        ctx.clearRect(0, 0, W, H);
        ctx.drawImage(img, (W - dw) * (layer.x ?? 50) / 100, (H - dh) * (layer.y ?? 50) / 100, dw, dh);
        const px = ctx.getImageData(0, 0, W, H).data;
        const g = layer.grade || [[1, 1, 1], [0, 0, 0]];
        const M = layer.light || [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
        const a = first ? 1 : layer.opacity;
        for (let i = 0, j = 0; i < px.length; i += 4, j += 3) {
          const r = lin(clamp(px[i] / 255 * g[0][0] + g[1][0]));
          const gg = lin(clamp(px[i + 1] / 255 * g[0][1] + g[1][1]));
          const b = lin(clamp(px[i + 2] / 255 * g[0][2] + g[1][2]));
          for (let k = 0; k < 3; k++) out[j + k] = out[j + k] * (1 - a) + unlin(clamp(M[k][0] * r + M[k][1] * gg + M[k][2] * b)) * a;
        }
        first = false;
      }
      const dim = look.dim || 0, cc = parseColor(getComputedStyle(this.stage.dim).backgroundColor) || [0.17, 0.17, 0.17];
      if (dim) for (let j = 0; j < out.length; j += 3) for (let k = 0; k < 3; k++) out[j + k] = out[j + k] * (1 - dim) + cc[k] * dim;
      return (this.painted = { key, out, W, H, SCALE, box });
    }

    // The mean colour under a rectangle (viewport px), with the panels it's on laid over it.
    under(p, r, fills) {
      const x0 = Math.max(0, Math.floor((r.left - p.box.left) * p.SCALE)), x1 = Math.min(p.W, Math.ceil((r.right - p.box.left) * p.SCALE));
      const y0 = Math.max(0, Math.floor((r.top - p.box.top) * p.SCALE)), y1 = Math.min(p.H, Math.ceil((r.bottom - p.box.top) * p.SCALE));
      const bg = [0, 0, 0];
      let n = 0;
      for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) {
        const j = (y * p.W + x) * 3;
        bg[0] += p.out[j]; bg[1] += p.out[j + 1]; bg[2] += p.out[j + 2]; n++;
      }
      if (!n) return null;
      let c = bg.map((v) => v / n);
      for (const f of fills) c = c.map((v, k) => v * (1 - f[3]) + f[k] * f[3]);
      return c;
    }

    // The fills over the picture behind a text run, back to front: panels behind it, then its
    // own see-through ancestors (the deck table's).
    fills(el, r) {
      const out = [];
      for (const panel of this.panels()) {
        const b = panel.getBoundingClientRect();
        if (r.left >= b.left && r.right <= b.right && r.top >= b.top && r.bottom <= b.bottom) {
          const f = parseColor(getComputedStyle(panel).backgroundColor);
          if (f && f[3] > 0) out.push(f);
        }
      }
      const own = [];
      for (let a = el; a && a !== this.root; a = a.parentElement) {   // the root's own background is behind the stage
        const f = parseColor(getComputedStyle(a).backgroundColor);
        if (f && f[3] > 0) own.unshift(f);
      }
      return out.concat(own);
    }

    // Every element with its own text: its colour as the page set it, and the worst
    // contrast with what's behind its text.
    texts(p) {
      const found = new Map();
      const walker = document.createTreeWalker(this.root, NodeFilter.SHOW_TEXT);
      for (let n = walker.nextNode(); n; n = walker.nextNode()) {
        const el = n.parentElement;
        if (!el || !n.textContent.trim() || el.closest("script, style, .keshiki-stage, .zero-count")) continue;
        const style = getComputedStyle(el);
        if (style.visibility === "hidden" || style.display === "none") continue;
        if (!this.touched.has(el)) this.original.set(el, style.color);
        const fg = parseColor(this.original.get(el) || style.color);
        if (!fg || fg[3] < 0.5) continue;
        const range = document.createRange();
        range.selectNodeContents(n);
        for (const r of range.getClientRects()) {
          if (r.width < 2 || r.height < 2) continue;
          const bg = this.under(p, r, this.fills(el, r));
          if (!bg) continue;
          const q = ratio(fg, bg);
          const was = found.get(el);
          if (!was || q < was.ratio) found.set(el, { fg: fg.slice(0, 3), bg, ratio: q });
        }
      }
      return found;
    }

    // Coloured text moved toward the theme's text (lighter in a dark theme: `up`), its hue
    // turned a little away from the colour behind it, until it reads or has moved its most.
    shift(fg, bg, up) {
      const lch = toOklch(fg);
      if (lch[1] < 0.04) return null;   // white, black or grey: only an outline helps
      const back = toOklch(bg);
      const apart = Math.atan2(Math.sin(lch[2] - back[2]), Math.cos(lch[2] - back[2]));
      const turn = back[1] < 0.02 ? 0 : apart >= 0 ? 1 : -1;
      let best = null;
      for (let d = 0.02; d <= MAX_SHIFT + 1e-9; d += 0.02) {
        best = fromOklch([clamp(lch[0] + (up ? d : -d)), lch[1], lch[2] + turn * MAX_HUE * (d / MAX_SHIFT)]);
        if (ratio(best, bg) >= AIM) break;
      }
      return best;
    }

    async adjust() {
      const p = await this.paint();
      const strength = (this.settings.strength ?? 60) / 100;
      const everywhere = this.settings.outline === "everywhere";
      const themeLight = luminance((parseColor(getComputedStyle(this.root).color) || [1, 1, 1]).slice(0, 3)) > 0.4;
      const want = new Map();
      this.report = [];
      for (const [el, t] of this.texts(p)) {
        let fg = t.fg, q = t.ratio, color = null;
        if (q < AIM) {
          const moved = this.shift(t.fg, t.bg, themeLight);
          if (moved && ratio(moved, t.bg) > q) { color = moved; fg = moved; q = ratio(moved, t.bg); }
        }
        // How short it still is (0-1), and the outline that makes up for it: as strong as it's
        // short, scaled by strength; everywhere also has a baseline. The text's opposite colour,
        // sized to the text: a crisp edge and a little soft spread.
        const short = q < AIM ? Math.min(1, (AIM - q) / (AIM - 1)) : 0;
        const alpha = Math.min(0.95, strength * (everywhere ? 0.5 + 0.5 * short : short ? 0.35 + 0.65 * short : 0));
        const halo = alpha > 0.02 ? (() => {
          const c = luminance(fg) > 0.4 ? "0, 0, 0" : "255, 255, 255";
          return `0 0 0.06em rgba(${c}, ${alpha.toFixed(2)}), 0 0 0.16em rgba(${c}, ${(alpha * 0.85).toFixed(2)})`;
        })() : null;
        this.report.push({ text: el.textContent.trim().slice(0, 30), before: +t.ratio.toFixed(2), after: +q.toFixed(2),
                           color: !!color, halo: !!halo });
        if (color || halo) want.set(el, { color, halo });
      }
      for (const el of [...this.touched.keys()]) if (!want.has(el) || !el.isConnected) this.restore(el);
      for (const [el, { color, halo }] of want) {
        if (!this.touched.has(el)) this.touched.set(el, [el.style.color, el.style.textShadow]);
        const own = this.touched.get(el);
        const c = color ? `rgb(${color.map((v) => Math.round(v * 255)).join(", ")})` : own[0];
        const sh = halo || own[1];
        if (el.style.color !== c) el.style.color = c;
        if (el.style.textShadow !== sh) el.style.textShadow = sh;
      }
    }

    restore(el) {
      const [color, shadow] = this.touched.get(el);
      el.style.color = color;
      el.style.textShadow = shadow;
      this.touched.delete(el);
    }

    clear() {
      for (const el of [...this.touched.keys()]) this.restore(el);
      this.report = [];
    }

    // Its own style writes don't count as the page changing.
    ours(record) {
      return record.type === "attributes" && record.attributeName === "style" && this.touched.has(record.target);
    }
  }

  // Anki's deck list: only while it's showing with backdrops on.
  let contrast = null;

  window.keshiki = {
    Stage,
    main: null,
    backdrops,
    backdrop,
    Contrast,
    get contrast() { return contrast; },
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
          backdrop.soon();
        };
        stage.onLook = (look) => {
          backdrop.set(look);
          // It reads the backdrop's settings when it runs: only on the deck list, with backdrops on.
          if (contrast) contrast.soon(60);
        };
        const start = () => {
          // The deck list's text (once there's a body: this runs in the page's head), with
          // Keshiki's add-on panel behind some of it.
          contrast = new Contrast(document.body, stage,
            () => [...document.querySelectorAll(".keshiki-panel")].filter((el) => el.style.display !== "none"),
            () => (backdrop.wasDecks && backdrop.settings ? backdrop.settings.text : null));
          backdrops.watch(document.body);
          backdrops.soon();
          backdrop.watch();
          backdrop.soon();
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
