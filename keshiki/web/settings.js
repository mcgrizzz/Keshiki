/* Keshiki's settings pages, on Kiso's settings shell (shell.js: S, saved, draft,
   page, h, call, changed, render, pageHead, slider, radio, openModal...).
   Python computes every look (settings_page.py), so the previews show exactly
   what the main window will. */

let images = [];       // the image library
let sel = null;        // selected scene id on the Scenes page
let scrub = null;      // scene editor position: minutes of day or percent done

const EVERY = [[0, "Each time Anki starts"], [15, "15 minutes"], [30, "30 minutes"], [60, "Hour"],
               [180, "3 hours"], [1440, "Day"]];
const KIND_NAMES = { single: "Single image", day: "Day cycle", progress: "Review progress" };
Object.assign(ICONS, {
  screens: "M3 5h18v12H3zM8 21h8M12 17v4",
  scenes: "M3 18l5-6 4 4 3-3 6 5M3 5h18v14H3zM15.5 9.5a1.5 1.5 0 1 0 0-.01",
  day: "M12 3v2M12 19v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M3 12h2M19 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4M12 8a4 4 0 1 0 0 8a4 4 0 1 0 0-8",
  close: "M6 6l12 12M18 6L6 18",
  trash: "M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3",
  play: "M8 5v14l11-7z",
  pause: "M8 5v14M16 5v14",
});

const sceneById = (id) => draft.scenes.find((s) => s.id === id);
const imageUrl = (name) => (images.find((i) => i.name === name) || {}).url;
const thumbUrl = (name) => (images.find((i) => i.name === name) || {}).thumb;
const bg = (url) => (url ? { backgroundImage: `url("${url}")` } : {});

function hhmm(minutes) {
  const m = ((Math.round(minutes) % 1440) + 1440) % 1440;
  return String(Math.floor(m / 60)).padStart(2, "0") + ":" + String(m % 60).padStart(2, "0");
}

function sceneThumb(scene) {
  const v = (scene.versions || []).find((v) => v.image);
  return v ? thumbUrl(v.image) : null;
}

function dropMissingScenes(d) {
  const ids = new Set(d.scenes.map((s) => s.id));
  for (const screen of Object.values(d.screens)) screen.scenes = screen.scenes.filter((id) => ids.has(id));
}

// -- previews -------------------------------------------------------------

const stages = new WeakMap();
function stageFor(box) {
  if (!stages.has(box)) stages.set(box, new keshiki.Stage(box, false));
  return stages.get(box);
}

function refreshPreviews() {
  for (const box of document.querySelectorAll("[data-screen]")) {
    call("look", { cfg: draft, screen: box.dataset.screen }).then((look) => {
      stageFor(box).apply(look && !look.error ? Object.assign(look, { fade: 400 }) : null);
      box.querySelector(".mock-empty").hidden = !!(look && look.layers);
    });
  }
  const preview = document.querySelector(".preview");
  if (preview) updateScenePreview(preview, true);
}

function mock(screen) {
  const box = h("div", { className: "mock", "data-screen": screen },
    h("div", { className: "mock-bar" }, h("span", { className: "mock-pill" }, "Decks Add Browse Stats Sync")),
    h("div", { className: "mock-empty", hidden: true }, screen === "study" ? "No background while studying"
      : screen === "done" ? "Pick scenes for when everything's done" : "No background"));
  if (screen !== "study") {
    box.append(h("div", { className: "mock-table" },
      [["Japanese", "120"], ["Kanji", "48"], ["Geography", "0"]].map(([name, due]) => [name, screen === "done" ? "0" : due])
        .map(([name, due]) =>
        h("div", { className: "mock-row" }, h("b", {}, name), h("span", {}, due)))));
  } else {
    box.append(h("div", { className: "mock-card" }, h("div", { className: "q", lang: "ja" }, "景色"), h("hr"), "scenery"),
      h("div", { className: "mock-buttons" }, ["Again", "Hard", "Good", "Easy"].map((b) => h("span", {}, b))));
  }
  return box;
}

// -- Screens page --------------------------------------------------------

function screensPage() {
  if (!draft.scenes.length) {
    return [...pageHead("Screens"), welcome()];
  }
  const study = draft.screens.study;
  return [
    ...pageHead("Screens", "Choose what shows behind the deck list and while you study. Edits preview in Anki's main window until you save."),
    h("div", { className: "two" },
      h("section", { className: "panel" },
        h("div", { className: "panel-head" }, h("h2", {}, "Deck list"), h("span", { className: "help" }, "Your decks, and while Anki starts")),
        mock("main"),
        sceneChooser(draft.screens.main),
        lookControls(draft.screens.main)),
      h("section", { className: "panel" },
        h("div", { className: "panel-head" }, h("h2", {}, "Studying"), h("span", { className: "help" }, "Overview, reviews and the finished screen")),
        mock("study"),
        h("label", { className: "check" },
          h("input", { type: "checkbox", checked: study.enabled, onchange: (e) => { study.enabled = e.target.checked; changed(true); } }),
          "Show a background while studying"),
        study.enabled && h("div", { className: "choices" },
          radio("source", study.same_as_main, "Same scenes as the deck list", () => { study.same_as_main = true; changed(true); }),
          radio("source", !study.same_as_main, "Scenes of its own", () => { study.same_as_main = false; changed(true); })),
        study.enabled && !study.same_as_main && sceneChooser(study),
        study.enabled && lookControls(study)),
      donePanel()),
  ];
}

// Once every deck is done for today, these scenes take over both screens.
function donePanel() {
  const done = draft.screens.done;
  return h("section", { className: "panel" },
    h("div", { className: "panel-head" }, h("h2", {}, "All done for today"),
      h("span", { className: "help" }, "Once there's nothing left to study in any deck")),
    mock("done"),
    h("label", { className: "check" },
      h("input", { type: "checkbox", checked: done.enabled, onchange: (e) => { done.enabled = e.target.checked; changed(true); } }),
      "Switch to these scenes when everything's done"),
    done.enabled && sceneChooser(done),
    done.enabled && lookControls(done),
    done.enabled && h("p", { className: "help" }, "For the deck list and studying alike. A new day, with new cards due, switches back."));
}

function welcome() {
  return h("div", { className: "panel blank" },
    h("h2", {}, "Start with a picture"),
    h("p", {}, "Add a few images and they'll appear behind Anki's main window. Later you can turn them into scenes that follow the time of day or your progress through today's reviews."),
    h("button", { type: "button", className: "primary", onclick: () => addImagesAsScenes(true) }, "Add images..."));
}

function sceneChooser(screen) {
  const options = draft.scenes.filter((s) => !screen.scenes.includes(s.id));
  const add = h("select", { "aria-label": "Add a scene", onchange: (e) => {
    if (e.target.value) { screen.scenes.push(e.target.value); changed(true); }
  } }, h("option", { value: "" }, screen.scenes.length ? "Add another..." : "Choose a scene..."),
     options.map((s) => h("option", { value: s.id }, s.name)));
  return [
    h("div", { className: "field" }, h("span", { className: "label" }, "Scenes"),
      h("div", { className: "chips" },
        screen.scenes.map((id) => {
          const scene = sceneById(id);
          const thumb = sceneThumb(scene);
          return h("span", { className: "chip" },
            thumb ? h("img", { src: thumb, alt: "" }) : h("span", { className: "swatch" }),
            h("span", { className: "chip-name", title: scene.name }, scene.name),
            h("button", { type: "button", "aria-label": `Remove ${scene.name}`, title: "Remove",
                          onclick: () => { screen.scenes = screen.scenes.filter((x) => x !== id); changed(true); } }, "×"));
        }),
        options.length ? add : null)),
    screen.scenes.length > 1 && h("div", { className: "field" }, h("label", {}, "Shuffle every"),
      h("select", { onchange: (e) => { screen.every = Number(e.target.value); changed(); } },
        EVERY.map(([v, label]) => h("option", { value: v, selected: screen.every === v }, label)))),
  ];
}

function lookControls(screen) {
  return [
    slider("Dim", screen.dim, 0, 90, "%", (v) => { screen.dim = v; }),
    slider("Blur", screen.blur, 0, 30, "px", (v) => { screen.blur = v; }),
  ];
}

// -- Scenes page ---------------------------------------------------------

function scenesPage() {
  loadMoments();
  if (!sceneById(sel)) sel = draft.scenes.length ? draft.scenes[0].id : null;
  const scene = sceneById(sel);
  return [
    ...pageHead("Scenes", "A scene is one picture, or versions of one picture that take turns through the day or as today's reviews get done."),
    h("div", { className: "scenes" },
      h("div", {},
        h("div", { className: "list-actions" },
          h("button", { type: "button", onclick: () => addImagesAsScenes(false) }, "Add images..."),
          h("button", { type: "button", onclick: () => addScene("day") }, "New day cycle")),
        h("div", { className: "scene-list" }, draft.scenes.map((s) =>
          h("button", { type: "button", className: "scene-item", "aria-current": s.id === sel ? "true" : "false",
                        onclick: () => { stopPlaying(); sel = s.id; scrub = null; call("end_moment"); render(); } },
            h("span", { className: "thumb", style: bg(sceneThumb(s)) }),
            h("span", { className: "item-name", title: s.name }, s.name), h("small", {}, KIND_NAMES[s.kind]))))),
      scene ? sceneEditor(scene) : h("div", { className: "panel blank" }, h("p", {}, "Add images or start a day cycle to make your first scene.")))];
}

async function addImagesAsScenes(useThem) {
  const res = await call("import");
  if (!res || res.error) return;
  images = res.images;
  for (const name of res.added) {
    const scene = await call("new_scene", { kind: "single", image: name });
    draft.scenes.push(scene);
    if (useThem || !draft.screens.main.scenes.length) draft.screens.main.scenes.push(scene.id);
    sel = sel || scene.id;
  }
  changed(true);
}

async function addScene(kind) {
  const scene = await call("new_scene", { kind });
  draft.scenes.push(scene);
  sel = scene.id;
  scrub = null;
  page = "scenes";
  changed(true);
}

async function deleteScene(scene) {
  const ok = await confirmDialog({ title: `Delete "${scene.name}"?`, yes: "Delete scene", danger: true,
    text: "It comes off every screen that shows it; its pictures stay. Until you save, Cancel brings it back." });
  if (!ok) return;
  stopPlaying();
  draft.scenes = draft.scenes.filter((s) => s !== scene);
  for (const screen of Object.values(draft.screens)) screen.scenes = screen.scenes.filter((id) => id !== scene.id);
  sel = null;
  changed(true);
}

function sceneEditor(scene) {
  pausePlaying();   // a redraw keeps the run; play carries on with it
  const preview = h("div", { className: "preview" },
    h("span", { className: "readout" }),
    scene.kind !== "single" && h("div", { className: "preview-controls" },
      h("button", { type: "button", id: "backToNow", hidden: scrub === null,
                    title: "Stop previewing this moment, here and in Anki's window",
                    onclick: () => { stopPlaying(); scrub = null; updateScenePreview(preview, false); } }, "Back to now"),
      h("select", { id: "playSpeed", "aria-label": "Timelapse length",
                    title: scene.kind === "day" ? "How long the whole day takes" : "How long a whole session takes",
                    onchange: (e) => {
                      playSeconds = Number(e.target.value);
                      if (playing) { pausePlaying(); play(scene, preview); }   // carry on at the new speed
                    } },
        PLAY_SPEEDS.map(([secs, label]) => h("option", { value: secs, selected: secs === playSeconds }, label))),
      h("button", { type: "button", className: "play", id: "play", "aria-label": "Play",
        title: scene.kind === "day" ? "Play the next 24 hours, here and in Anki's window"
                                    : "Play on to finished, here and in Anki's window",
        onclick: () => (playing ? pausePlaying() : play(scene, preview)) }, icon("play"))));
  const panel = h("section", { className: "panel editor" },
    h("div", { className: "editor-head" },
      h("input", { type: "text", className: "name", value: scene.name, "aria-label": "Scene name", "data-field": scene.id,
                   oninput: (e) => {
                     scene.name = e.target.value;
                     const item = document.querySelector(".scene-item[aria-current=true] .item-name");
                     if (item) { item.textContent = scene.name; item.title = scene.name; }
                     changed();
                   } }),
      h("span", { className: "kind" }, KIND_NAMES[scene.kind]),
      h("button", { type: "button", className: "danger", id: "deleteScene", onclick: () => deleteScene(scene) },
        icon("trash"), "Delete scene")),
    preview);
  if (scene.kind !== "single") panel.append(ribbon(scene, preview));
  panel.append(versionTable(scene, preview));
  return panel;
}

// One line per version: picture, name, when it starts, how long it fades in.
function versionTable(scene, preview) {
  if (scene.kind === "single") {
    const v = scene.versions[0];
    return h("div", { className: "versions single" },
      pickButton(v), h("span", { className: "file" }, v.image || "No image yet"),
      h("button", { type: "button", onclick: () => pickImage(v.image, (name) => { v.image = name; changed(true); }) },
        v.image ? "Change image..." : "Choose image..."));
  }
  const day = scene.kind === "day";
  const table = h("div", { className: "versions" },
    h("div", { className: "vhead" }, h("span"), h("span", {}, "Version"), h("span", {}, day ? "Starts" : "Starts at"),
      h("span", {}, day ? "Fully in" : "Fades in over"), h("span")),
    scene.versions.map((v, i) => versionRow(scene, v, i, preview)));
  table.append(h("button", { type: "button", className: "add-version", onclick: () => {
    const last = scene.versions[scene.versions.length - 1] || {};
    scene.versions.push(day
      ? { label: "", image: "", anchor: "sun", direction: "setting", from: 0, to: -6 }
      : { label: "", image: "", at: Math.min(100, (Number(last.at) || 0) + 10), fade: 10 });
    changed(true);
  } }, "+ Add version"));
  return table;
}

function pickButton(v, scene = null, index = -1) {
  return h("button", { type: "button", className: "pick" + (v.image ? "" : " empty"), style: bg(thumbUrl(v.image)),
                       title: v.image ? `Change image (${v.image})` : "Choose image",
                       "aria-label": v.image ? `Change image (${v.image})` : "Choose image",
                       onclick: () => pickImage(v.image, (name) => { v.image = name; changed(true); }, scene, index) },
    v.image ? "" : "+");
}

// Where a version is fully in: its start plus its fade (it holds from there).
// Day versions come from the last preview's marks, which Python works out from the sun.
function versionPosition(scene, v, i) {
  if (scene.kind === "progress") return Math.min(100, (Number(v.at) || 0) + (Number(v.fade) || 0));
  const mark = (S.marks || []).find((m) => m.index === i);
  return mark ? (mark.start + mark.fade) % 1440 : currentPosition(scene);
}

// The sun's named moments with today's times (Python's SUN_MOMENTS), fetched for the
// day settings they were worked out from.
let moments = [];
let momentsFor = null;
function loadMoments() {
  const key = JSON.stringify(draft.day);
  if (key === momentsFor) return;
  momentsFor = key;
  call("moments", { day: draft.day }).then((list) => {
    if (!Array.isArray(list)) return;
    moments = list;
    if (page === "scenes") render();
  });
}

// A day version's start and finish are moments of one half of the day: the morning
// (rising sun, up to noon) or the evening (from noon, setting). Values are "direction:degrees".
const half = (direction) => moments.filter((m) => m.direction === direction || (direction === "setting" && m.key === "noon"));
const momentValue = (direction, degrees) => `${direction}:${degrees}`;
function momentOption(m, direction, selected) {
  return h("option", { value: momentValue(direction, m.degrees), selected }, `${m.name} · ${hhmm(m.time)}`);
}
// A height that isn't one of the named moments (set in an older version) stays choosable.
function customOption(direction, degrees) {
  return h("option", { value: momentValue(direction, degrees), selected: true },
    `Sun at ${degrees}° (${direction === "rising" ? "morning" : "evening"})`);
}
function isMoment(direction, degrees) {
  return half(direction).some((m) => m.degrees === degrees);
}

function versionRow(scene, v, i, preview) {
  const num = (key, min, max, unit, label) => h("span", { className: "unit" },
    h("input", { type: "number", min, max, value: v[key], "aria-label": label,
                 onchange: (e) => { v[key] = Number(e.target.value) || 0; changed(true); } }), unit);
  let starts, fade;
  if (scene.kind === "day") {
    const clock = v.anchor === "clock";
    const direction = v.direction || "rising";
    const from = Number(v.from), to = Number(v.to);
    // Later in its half of the day: higher in the morning, lower in the evening (noon starts the evening).
    const after = (m) => (direction === "rising" ? m.degrees > from : m.key !== "noon" && m.degrees < from);
    starts = h("span", { className: "unit" },
      h("select", { "aria-label": "Starts", onchange: (e) => {
        const mark = (S.marks || []).find((m) => m.index === i);
        if (e.target.value === "clock") {
          // Keep today's times when moving from the sun to the clock.
          Object.assign(v, { anchor: "clock", offset: Math.round(mark ? mark.start : 0), fade: Math.round(mark ? mark.fade : 30) });
          delete v.direction; delete v.from; delete v.to;
        } else {
          const [dir, deg] = e.target.value.split(":");
          const was = { direction: v.direction, to: v.to };
          Object.assign(v, { anchor: "sun", direction: dir, from: Number(deg) });
          delete v.offset; delete v.fade;
          // Keep the finish if it still comes after; otherwise the next moment.
          const later = half(dir).filter((m) => (dir === "rising" ? m.degrees > v.from : m.key !== "noon" && m.degrees < v.from));
          if (was.direction !== dir || !later.some((m) => m.degrees === was.to)) v.to = later.length ? later[0].degrees : v.from;
        }
        changed(true);
      } },
        h("optgroup", { label: "Morning" }, half("rising").map((m) =>
          momentOption(m, "rising", !clock && direction === "rising" && m.degrees === from))),
        h("optgroup", { label: "Evening" }, half("setting").map((m) =>
          momentOption(m, "setting", !clock && direction === "setting" && m.degrees === from))),
        !clock && moments.length > 0 && !isMoment(direction, from) && customOption(direction, from),
        h("option", { value: "clock", selected: clock }, "At a set time")),
      clock && h("input", { type: "time", value: hhmm(v.offset), "aria-label": "Starts at",
                            onchange: (e) => {
                              if (!e.target.value) return;   // mid-edit, the box can be empty for a moment
                              const [hh, mm] = e.target.value.split(":").map(Number);
                              v.offset = hh * 60 + mm;
                              changed();   // no rebuild: the box keeps its focus; the timeline redraws on its own
                            } }));
    fade = clock
      ? h("span", { className: "unit" },
          h("input", { type: "number", min: 0, max: 720, value: v.fade, "aria-label": "Minutes until fully in",
                       onchange: (e) => { v.fade = Number(e.target.value) || 0; changed(); } }), "min later",
          h("small", { className: "when-time" }))
      : h("select", { "aria-label": "Fully in at", onchange: (e) => { v.to = Number(e.target.value.split(":")[1]); changed(true); } },
          half(direction).filter(after).map((m) => momentOption(m, direction, m.degrees === to)),
          moments.length > 0 && !isMoment(direction, to) && customOption(direction, to));
  } else {
    starts = num("at", 0, 100, "% done", "Starts at percent done");
    fade = num("fade", 0, 100, "%", "Fade-in percent");
  }
  // Working on a version's fields shows that version in the preview.
  return h("div", { className: "version", "data-index": i,
                    onfocusin: () => {
                      if (playing) return;
                      run = null;
                      scrub = versionPosition(scene, v, i);
                      updateScenePreview(preview, false);
                    } },
    pickButton(v, scene, i),
    h("input", { type: "text", className: "label", value: v.label, placeholder: "Name", "aria-label": "Version name",
                 oninput: (e) => { v.label = e.target.value; }, onchange: () => changed() }),
    starts, fade,
    h("button", { type: "button", className: "icon-only", title: "Remove version", "aria-label": "Remove version",
                  onclick: () => { scene.versions.splice(i, 1); changed(true); } }, icon("close")));
}

// Timelapse: one play-pause button. A day cycle plays the next 24 hours from now
// (or from where the scrubber was left) and ends back at now; a progress scene
// plays on to finished. Pause keeps the run, so play carries on with it.
const PLAY_SPEEDS = [[5, "5 s"], [10, "10 s"], [30, "30 s"], [60, "1 min"], [300, "5 min"]];
let playSeconds = 10;   // how long a whole run takes
let playing = null;     // the animation frame while it plays
let run = null;         // {pos, end}: the run under way, playing or paused; minutes run on past midnight

function play(scene, preview) {
  const day = scene.kind === "day";
  const span = day ? 1440 : 100;
  if (!run) {
    const from = currentPosition(scene);
    run = day ? { pos: from, end: from + 1440 } : { pos: from < 100 ? from : 0, end: 100 };
  }
  const perMs = span / (playSeconds * 1000);
  let last = performance.now();
  let busy = false;
  setPlayButton(scene, true);
  playing = { frame: 0 };
  const step = (now) => {
    if (!playing) return;
    run.pos = Math.min(run.end, run.pos + (now - last) * perMs);
    last = now;
    const done = run.pos >= run.end;
    if (!busy || done) {
      busy = true;
      // Back where it started: a day hands back to "now".
      // Fractional, so a slow run moves smoothly instead of a minute at a time.
      scrub = done && day ? null : day ? run.pos % 1440 : Math.min(run.pos, 100);
      updateScenePreview(preview, false).then(() => { busy = false; });
    }
    if (done) { run = null; pausePlaying(); }
    else playing.frame = requestAnimationFrame(step);
  };
  playing.frame = requestAnimationFrame(step);
}

function pausePlaying() {
  if (playing) cancelAnimationFrame(playing.frame);
  playing = null;
  const scene = sceneById(sel);
  if (scene) setPlayButton(scene, false);
}

// Stop and forget the run: the next play starts afresh.
function stopPlaying() {
  pausePlaying();
  run = null;
}

function setPlayButton(scene, on) {
  const button = document.getElementById("play");
  if (!button) return;
  button.classList.toggle("on", on);
  button.replaceChildren(icon(on ? "pause" : "play"));
  button.setAttribute("aria-label", on ? "Pause" : "Play");
  button.title = on ? "Pause" : scene.kind === "day"
    ? "Play the next 24 hours, here and in Anki's window" : "Play on to finished, here and in Anki's window";
}

// The ribbon: each version's image along the axis, fading in where its fade runs.
function ribbon(scene, preview) {
  const day = scene.kind === "day";
  const span = day ? 1440 : 100;
  const box = h("div", { className: "ribbon" });
  const ticks = h("div", { className: "ticks" });
  const hand = h("div", { className: "hand" });
  const input = h("input", { type: "range", min: 0, max: span, step: day ? 5 : 1, "aria-label": day ? "Time of day" : "Percent done",
                             oninput: (e) => { stopPlaying(); scrub = Number(e.target.value); updateScenePreview(preview, false); } });
  box.append(hand, input);
  box.dataset.span = span;
  return h("div", { className: "ribbon-wrap" }, box, ticks);
}

function drawRibbon(wrap, res, scene) {
  const day = scene.kind === "day";
  const span = day ? 1440 : 100;
  const box = wrap.querySelector(".ribbon");
  for (const seg of box.querySelectorAll(".seg")) seg.remove();
  const pct = (x) => (100 * x) / span;
  const add = (image, a, b, z, fade) => {
    if (b <= a || b <= 0) return;
    const seg = h("div", { className: "seg", style: Object.assign(bg(thumbUrl(image)), {
      left: pct(a) + "%", width: pct(b - a) + "%", zIndex: String(z) }) });
    if (fade > 0) seg.style.maskImage = `linear-gradient(to right, transparent, black ${(100 * fade) / (b - a)}%)`;
    box.prepend(seg);
  };
  const marks = res.marks;
  marks.forEach((m, i) => {
    // Each version runs from its start to the next one's (wrapping past midnight
    // on a day), fading in over the previous version, which runs on beneath it.
    const end = i + 1 < marks.length ? marks[i + 1].start : (day ? marks[0].start + 1440 : 100);
    const fade = !day && i === 0 ? 0 : Math.min(m.fade, end - m.start);
    const prev = marks[(i - 1 + marks.length) % marks.length];
    for (const shift of day ? [0, -1440] : [0]) {
      add(m.image, m.start + shift, Math.min(end + shift, span), 2 * i + 2, fade);
      if (fade) add(prev.image, m.start + shift, Math.min(m.start + fade + shift, span), 2 * i + 1, 0);
    }
  });
  const ticks = wrap.querySelector(".ticks");
  const labels = day
    ? [[0, "00:00"], [res.anchors.sunrise, "Sunrise " + hhmm(res.anchors.sunrise), "sun"], [720, "12:00"],
       [res.anchors.sunset, "Sunset " + hhmm(res.anchors.sunset), "sun"], [1440, "24:00"]]
    : [[0, "Start"], [50, "Half done"], [100, "Finished"]];
  // Drop round-hour labels that would collide with sunrise or sunset.
  const px = box.clientWidth || 600;
  const shown = labels.filter((l) => l[2] || !labels.some((o) => o[2] && (Math.abs(o[0] - l[0]) / span) * px < 100));
  ticks.replaceChildren(...shown.sort((x, y) => x[0] - y[0]).map(([at, text, cls]) =>
    h("span", { className: cls || "", style: { left: pct(at) + "%" } }, text)));
}

function currentPosition(scene) {
  if (scrub !== null) return scrub;
  if (scene.kind === "progress") return Math.round(S.percent);
  const now = new Date();
  return now.getHours() * 60 + now.getMinutes();
}

function updateScenePreview(preview, redrawRibbon) {
  const scene = sceneById(sel);
  if (!scene) return Promise.resolve();
  const position = currentPosition(scene);
  const wrap = preview.parentElement.querySelector(".ribbon-wrap");
  if (wrap) {
    const span = Number(wrap.querySelector(".ribbon").dataset.span);
    wrap.querySelector(".hand").style.left = (100 * position) / span + "%";
    wrap.querySelector("input").value = position;
  }
  const readout = preview.querySelector(".readout");
  readout.textContent = scene.kind === "day" ? (scrub === null ? "Now, " : "") + hhmm(position)
    : scene.kind === "progress" ? (position >= 100 ? "Finished" : `${Math.round(position)}% done`) : "";
  readout.hidden = scene.kind === "single";
  const back = document.getElementById("backToNow");
  if (back) back.hidden = scrub === null;
  // A chosen moment shows in Anki's window too; back to now hands it back to the screen's own look.
  // While playing, each step eases into the next instead of jumping.
  const ease = playing ? 160 : 0;
  return call("compose", { scene, day: draft.day, light: draft.light, position, images: draft.images,
                           show: scrub !== null, cfg: draft, fade: ease }).then((res) => {
    // A late answer for a scene no longer on screen changes nothing.
    if (!res || res.error || sceneById(sel) !== scene || !preview.isConnected) return;
    S.anchors = res.anchors;
    S.marks = res.marks;
    stageFor(preview).apply({ layers: res.layers, light: res.light, dim: 0, blur: 0, fade: redrawRibbon ? 300 : ease },
                            !redrawRibbon && !ease);
    for (const m of res.marks) {
      const cell = document.querySelector(`.version[data-index="${m.index}"] .when-time`);
      if (cell) cell.textContent = `${hhmm(m.start)}–${hhmm(m.start + m.fade)}`;
    }
    if (wrap && redrawRibbon) drawRibbon(wrap, res, scene);
    // Highlight the version on top right now.
    const top = res.layers.length ? res.layers[res.layers.length - 1].image : null;
    for (const row of document.querySelectorAll(".version[data-index]")) {
      const v = scene.versions[Number(row.dataset.index)];
      row.classList.toggle("showing", !!top && !!v && v.image === top);
    }
  });
}

// -- image picker ---------------------------------------------------------

// Opened from a version of a scene, the picker can keep the scene's pictures lined
// up: one position (the part of each picture kept in view) for all of them, so they
// match through the fades. Positions belong to pictures (draft.images), so lining up
// writes the same position to each. scene.aligned === false: the user turned it off.
function pickImage(current, use, scene = null, index = -1) {
  let chosen = current || (images[0] && images[0].name) || null;
  const grid = h("div", { className: "grid" });
  const side = h("div", {});
  const CENTRE = { x: 50, y: 50 };
  const where = (name) => draft.images[name] || CENTRE;
  const same = (a, b) => a.x === b.x && a.y === b.y;
  // The scene's other versions, one each whatever is selected (two can share a picture),
  // and the pictures that move with the chosen one.
  const otherVersions = scene ? scene.versions.filter((v, j) => j !== index && v.image) : [];
  const others = () => [...new Set(otherVersions.map((v) => v.image))].filter((name) => name !== chosen);
  // Ticked only when it's true: the pictures already share one position.
  let linked = !!scene && scene.aligned !== false && otherVersions.length > 0
    && others().every((name) => same(where(name), where(current || others()[0])));
  // Lined up, every picture shows the scene's position; otherwise each its own.
  const focus = (name = chosen) => (linked && others().length ? where(others()[0]) : where(name));
  const fitOf = (img) => {
    const a = S.window[0] / S.window[1], i = img.naturalWidth / img.naturalHeight;
    return i > a ? { w: a / i, h: 1 } : { w: 1, h: i / a };
  };
  const frameAt = (frame, img, f) => {
    if (!img.naturalWidth) return;
    const { w, h: fh } = fitOf(img);
    Object.assign(frame.style, { left: f.x * (1 - w) + "%", top: f.y * (1 - fh) + "%",
                                 width: 100 * w + "%", height: 100 * fh + "%" });
  };

  const drawSide = () => {
    if (!chosen) { side.replaceChildren(h("p", { className: "help" }, "Add images to choose from.")); return; }
    // The frame is the part of the picture Anki's window shows: cropped to the window's
    // shape, and placed by the image's focus point (CSS background-position).
    const frame = h("span", { className: "crop-frame" });
    const img = h("img", { src: imageUrl(chosen), alt: "", draggable: false });
    const box = h("div", { className: "focus-box" }, img, frame);
    const help = h("p", { className: "help" });
    const fit = () => fitOf(img);

    // The scene's other pictures, small, each with its frame: they follow the drag while lined up.
    const minis = otherVersions.map((v) => {
      const mimg = h("img", { src: thumbUrl(v.image), alt: "", draggable: false });
      const mframe = h("span", { className: "crop-frame" });
      mimg.addEventListener("load", () => place());
      return { name: v.image, img: mimg, frame: mframe,
               el: h("div", { className: "mini-item", title: v.image },
                 h("div", { className: "mini" }, mimg, mframe), h("span", { className: "mini-label" }, v.label || v.image)) };
    });
    const shapeNote = h("p", { className: "help shape-note", hidden: true },
      "These pictures have different shapes, so they line up only roughly.");
    const toggle = h("input", { type: "checkbox", id: "alignPictures", checked: linked, onchange: (e) => {
      linked = e.target.checked;
      if (linked) {
        // Line the others up with the picture in view.
        const f = { ...where(chosen) };
        for (const name of others()) draft.images[name] = { ...f };
        delete scene.aligned;
      } else scene.aligned = false;
      changed();
      place();
    } });
    const align = minis.length && h("div", { className: "align" },
      h("label", { className: "check" }, toggle, "Keep the scene's pictures lined up"),
      h("div", { className: "minis" }, ...minis.map((m) => m.el)),
      shapeNote);

    const place = () => {
      if (!img.naturalWidth) return;
      const { w, h: fh } = fit();
      frameAt(frame, img, focus());
      const crops = w < 0.995 || fh < 0.995;
      box.classList.toggle("fixed", !crops);
      help.textContent = crops
        ? "The frame is what Anki's window shows of this picture. Drag it, or click, to choose the part that stays in view."
        : "This picture has the same shape as Anki's window, so all of it shows.";
      if (!align) return;
      align.hidden = !crops;
      align.classList.toggle("linked", linked);
      for (const m of minis) frameAt(m.frame, m.img, linked ? focus() : where(m.name));
      const ratio = img.naturalWidth / img.naturalHeight;
      shapeNote.hidden = !minis.some((m) => m.img.naturalWidth
        && Math.abs(m.img.naturalWidth / m.img.naturalHeight / ratio - 1) > 0.02);
    };
    img.addEventListener("load", place);
    // Click or drag: the frame's centre follows the pointer, kept inside the picture.
    const move = (e) => {
      const r = box.getBoundingClientRect(), { w, h: fh } = fit();
      const axis = (pos, size, span) => (span >= 0.995 ? 50
        : Math.round((100 * Math.min(Math.max(pos / size - span / 2, 0), 1 - span)) / (1 - span)));
      const f = { x: axis(e.clientX - r.left, r.width, w), y: axis(e.clientY - r.top, r.height, fh) };
      for (const name of linked ? [chosen, ...others()] : [chosen]) draft.images[name] = { ...f };
      place();
    };
    box.addEventListener("pointerdown", (e) => {
      if (box.classList.contains("fixed")) return;
      box.setPointerCapture(e.pointerId);
      move(e);
      box.onpointermove = move;
    });
    box.addEventListener("pointerup", () => { box.onpointermove = null; changed(); });
    const used = draft.scenes.some((sc) => sc.versions.some((v) => v.image === chosen));
    side.replaceChildren(box, help, align || "",
      h("div", { className: "image-meta" }, h("span", { className: "muted", title: chosen }, chosen),
        used ? h("span", { className: "muted" }, "Used by a scene")
          : h("button", { type: "button", className: "link danger", id: "deleteImage", onclick: async () => {
              const ok = await confirmDialog({ title: "Delete this picture?", yes: "Delete picture", danger: true,
                text: "It's removed from Keshiki's picture folder right away; Cancel can't bring it back." });
              if (!ok) return;
              const res = await call("delete_image", chosen);
              images = res.images;
              delete draft.images[chosen];
              chosen = images[0] ? images[0].name : null;
              drawGrid(); drawSide(); changed();
            } }, "Delete image")));
    place();
  };
  // Choosing a picture while lined up gives it the scene's position.
  const choose = (name) => {
    closeModal();
    if (linked && others().length && draft.images[others()[0]]) draft.images[name] = { ...draft.images[others()[0]] };
    use(name);
  };
  const drawGrid = () => grid.replaceChildren(...images.map((img) =>
    h("button", { type: "button", className: "tile", style: bg(img.thumb), title: img.name, "aria-label": img.name,
                  "aria-pressed": img.name === chosen ? "true" : "false",
                  onclick: () => { chosen = img.name; drawGrid(); drawSide(); },
                  ondblclick: () => choose(img.name) })));

  openModal(h("div", { className: "dialog" },
    h("div", { className: "dialog-head" }, h("h2", {}, "Choose an image"),
      h("button", { type: "button", onclick: async () => {
        const res = await call("import");
        if (!res || res.error) return;
        images = res.images;
        if (res.added.length) chosen = res.added[0];
        drawGrid(); drawSide();
      } }, "Add images..."),
      h("button", { type: "button", className: "link", onclick: () => call("open_folder") }, "Open folder")),
    h("div", { className: "picker" }, grid, side),
    h("div", { className: "dialog-foot" },
      h("button", { type: "button", onclick: closeModal }, "Cancel"),
      h("button", { type: "button", className: "primary", onclick: () => { if (chosen) choose(chosen); else closeModal(); } },
        "Use image"))));
  drawGrid(); drawSide();
}

// -- Day & time page -----------------------------------------------------

// A location lookup in flight, or the last one's error.
let locating = false;
let locateError = "";

function locate() {
  locating = true;
  locateError = "";
  call("locate");
  render();
}

window.keshikiLocated = (res) => {
  locating = false;
  if (res.error) locateError = res.error;
  else Object.assign(draft.day, { latitude: res.latitude, longitude: res.longitude, place: res.place });
  changed(true);
};

function dayPage() {
  const day = draft.day;
  const loc = day.source === "location";
  const sunNote = h("div", { className: "help" });
  if (loc) {
    call("sun", day).then((t) => {
      sunNote.textContent = t ? `Today here: sunrise ${hhmm(t.sunrise)}, sunset ${hhmm(t.sunset)}.`
        : "The sun doesn't rise or set here today, so the times below stand in.";
    });
  }
  const coord = (key, label, limit) => h("div", { className: "field" }, h("label", {}, label),
    h("input", { type: "number", step: "0.01", min: -limit, max: limit, value: day[key] ?? "", "data-field": key,
                 style: { width: "120px" },
                 onchange: (e) => {
                   day[key] = e.target.value === "" ? null : Number(e.target.value);
                   day.place = "";   // typed by hand: the looked-up name no longer fits
                   changed(true);
                 } }));
  const time = (key, label) => h("div", { className: "field" }, h("label", {}, label),
    h("input", { type: "time", value: day[key], "data-field": key, style: { width: "120px" },
                 onchange: (e) => { day[key] = e.target.value; changed(); } }));
  return [
    ...pageHead("Day & time", "Day-cycle scenes follow the sun's height through the day. Use the real sun where you are, or set your own day."),
    h("section", { className: "panel" },
      h("h2", {}, "Sunrise and sunset"),
      h("div", { className: "choices" },
        radio("daysource", !loc, "Times I set", () => { day.source = "manual"; changed(true); }),
        radio("daysource", loc, "The sun where I am", () => {
          day.source = "location";
          changed(true);
        })),
      loc
        ? [h("div", { className: "field" }, h("span", { className: "label" }, "Location"),
             h("div", { className: "locate" },
               h("span", {}, locating ? "Finding your location..." : day.place ? `Near ${day.place}`
                 : day.latitude != null ? "Your coordinates" : "Not set yet"),
               h("button", { type: "button", id: "locate", disabled: locating, onclick: locate },
                 day.latitude != null ? "Find again" : "Find my location"))),
           locateError && h("div", { className: "field" }, h("span"), h("div", { className: "error" }, locateError)),
           coord("latitude", "Latitude", 90), coord("longitude", "Longitude", 180),
           h("div", { className: "field" }, h("span"), h("div", {}, sunNote,
             h("div", { className: "help" }, "Find my location looks up a rough position from your internet address "
               + "(ipapi.co), only when you click it. You can also type coordinates from any map app: north and east are positive.")))]
        : [time("sunrise", "Sunrise"), time("sunset", "Sunset"),
           h("div", { className: "field" }, h("span"), h("div", { className: "help" },
             "Make these your own day: if your morning starts at 9, set sunrise to 09:00 and dawn arrives with you."))],
      loc && [time("sunrise", "Fallback sunrise"), time("sunset", "Fallback sunset")]),
    lightPanel(),
    h("section", { className: "panel" },
      h("h2", {}, "Transitions"),
      slider("Crossfade", draft.transition_seconds, 0, 10, " s", (v) => { draft.transition_seconds = v; }),
      h("div", { className: "field" }, h("span"), h("div", { className: "help" },
        "How long the background takes to change when you switch screens or a shuffle picks the next scene."))),
  ];
}

// Light: lighting the pictures by the sun, with a strength.
function lightPanel() {
  const l = draft.light;
  const strip = h("div", { className: "daylight" });
  const ticks = h("div", { className: "ticks" });
  const drawStrip = () => call("daylight", { day: draft.day, strength: l.tint_strength }).then((res) => {
      if (!res || res.error) return;
      // A light grey wall through today, under the light at this strength.
      const n = res.samples.length - 1;
      strip.style.background = `linear-gradient(to right, ${res.samples.map((c, i) => `${c} ${((100 * i) / n).toFixed(2)}%`).join(", ")})`;
      const pct = (m) => (100 * m) / 1440 + "%";
      ticks.replaceChildren(h("span", { style: { left: "0%" } }, "00:00"),
        h("span", { className: "sun", style: { left: pct(res.anchors.sunrise) } }, "Sunrise " + hhmm(res.anchors.sunrise)),
        h("span", { className: "sun", style: { left: pct(res.anchors.sunset) } }, "Sunset " + hhmm(res.anchors.sunset)),
        h("span", { style: { left: "100%" } }, "24:00"));
  });
  if (l.tint) drawStrip();
  const toggle = (key, label) => h("label", { className: "check" },
    h("input", { type: "checkbox", checked: l[key], onchange: (e) => { l[key] = e.target.checked; changed(true); } }), label);
  return h("section", { className: "panel" },
    h("h2", {}, "Light"),
    toggle("tint", "Light the pictures by the sun"),
    h("p", { className: "help indent" }, "Warm, low sun around sunrise and sunset, plain light at midday, the blue of "
      + "twilight, then a dim, faded night, the way eyes see in the dark. It follows the sun's height: for your "
      + "location, or the sunrise and sunset times above. Works on any scene, even a single picture."),
    l.tint && [slider("Strength", l.tint_strength, 0, 100, "%", (v) => { l.tint_strength = v; drawStrip(); }),
               h("div", { className: "field" }, h("span", { className: "label" }, "Today"),
                 h("div", {}, strip, ticks)),
               slider("Bloom", l.bloom, 0, 100, "%", (v) => { l.bloom = v; }),
               h("div", { className: "field" }, h("span"), h("div", { className: "help" },
                 "At night, pictures that show night keep their own lights (windows, lamps, stars) a little brighter "
                 + "than the rest. Bloom is the soft glow around them."))],
  );
}

// -- pages ------------------------------------------------------------------

let pushTimer = null;

Kiso.setup({
  prefix: "keshiki",
  brand: () => [h("b", { lang: "ja" }, "景色"), h("span", {}, "Keshiki")],
  pages: [
    {
      id: "screens", title: "Screens", icon: "screens", render: screensPage,
      slice: (d) => d.screens,
      revert: (d) => { d.screens = clone(saved.screens); dropMissingScenes(d); },
      // Dim, blur and shuffle go back to defaults; which scenes show stays.
      restore: (d) => {
        for (const [key, screen] of Object.entries(d.screens)) {
          const kept = { scenes: screen.scenes };
          if ("same_as_main" in screen) kept.same_as_main = screen.same_as_main;
          d.screens[key] = Object.assign(clone(S.defaults.screens[key]), kept);
        }
      },
      restoreTitle: "Dim, blur and shuffle back to their defaults; your scenes stay. Nothing changes until Save.",
    },
    {
      // No Restore for Scenes: the default is no scenes at all.
      id: "scenes", title: "Scenes", icon: "scenes", render: scenesPage,
      slice: (d) => [d.scenes, d.images],
      revert: (d) => {
        // New scenes a screen still uses stay, so reverting here can't change another page.
        const used = new Set(Object.values(d.screens).flatMap((s) => s.scenes));
        const kept = d.scenes.filter((s) => used.has(s.id) && !saved.scenes.some((x) => x.id === s.id));
        d.scenes = clone(saved.scenes).concat(kept);
        d.images = clone(saved.images);
      },
    },
    {
      id: "day", title: "Day & time", icon: "day", render: dayPage,
      slice: (d) => [d.day, d.transition_seconds, d.light],
      revert: (d) => { d.day = clone(saved.day); d.transition_seconds = saved.transition_seconds; d.light = clone(saved.light); },
      restore: (d) => {
        d.day = clone(S.defaults.day);
        d.transition_seconds = S.defaults.transition_seconds;
        d.light = clone(S.defaults.light);
      },
    },
  ],
  unsaved: (pages) => `Unsaved changes on ${pages}, previewing in the main window`,
  onLoad: (state) => {
    S.anchors = { sunrise: 390, sunset: 1170 };
    S.window = S.window || [16, 10];
    images = state.images;
  },
  // Unsaved edits preview live in the main window (and in the page's own previews).
  onChange: (dirty) => {
    clearTimeout(pushTimer);
    pushTimer = setTimeout(() => {
      call("draft", dirty ? draft : null);
      refreshPreviews();
    }, 120);
  },
  beforeRender: (p) => { if (p !== "scenes") { stopPlaying(); call("end_moment"); } },
  afterRender: () => refreshPreviews(),
  onCancel: () => stopPlaying(),
  onSaveError: (err) => { if (err.page === "scenes") sel = err.field; },
});
