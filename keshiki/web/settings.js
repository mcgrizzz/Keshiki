/* Keshiki's settings pages, on Kiso's settings shell (shell.js: S, saved, draft,
   page, h, call, changed, render, pageHead, slider, radio, openModal...).
   Python computes every look (settings_page.py), so the previews show exactly
   what the main window will. */

let images = [];       // the image library
let linked = {};       // linked folders' pictures (not in the library): name -> {url, thumb}
let trashed = [];      // pictures in the trash
let sel = null;        // selected scene id on the Scenes page
let scrub = null;      // scene editor position: minutes of day or percent done

const EVERY = [[0, "Each time Anki starts"], [15, "15 minutes"], [30, "30 minutes"], [60, "Hour"],
               [180, "3 hours"], [1440, "Day"]];
const KIND_NAMES = { single: "Single image", day: "Day cycle", progress: "Review progress", album: "Album" };
// An album's pictures that can show (a picture still to choose takes no turn).
const albumPictures = (scene) => scene.versions.filter((v) => v.image);
const kindLabel = (scene) => (scene.kind === "album"
  ? `Album · ${albumPictures(scene).length} picture${albumPictures(scene).length === 1 ? "" : "s"}` : KIND_NAMES[scene.kind]);
// How many turns a screen's shuffle has: one per scene, one per picture of an album.
const screenTurns = (screen) => screen.scenes.reduce((n, id) => {
  const scene = sceneById(id);
  return n + (!scene ? 0 : scene.kind === "album" ? albumPictures(scene).length : 1);
}, 0);
Object.assign(ICONS, {
  screens: "M3 5h18v12H3zM8 21h8M12 17v4",
  scenes: "M3 18l5-6 4 4 3-3 6 5M3 5h18v14H3zM15.5 9.5a1.5 1.5 0 1 0 0-.01",
  day: "M12 3v2M12 19v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M3 12h2M19 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4M12 8a4 4 0 1 0 0 8a4 4 0 1 0 0-8",
  close: "M6 6l12 12M18 6L6 18",
  hide: "M3 3l18 18M10.6 10.6a2 2 0 0 0 2.8 2.8M9.9 5.2A9.6 9.6 0 0 1 12 5c5 0 8.7 4.2 10 7a14 14 0 0 1-2.6 3.6M6.6 6.6C4.4 8 2.9 10.2 2 12c1.3 2.8 5 7 10 7a9.7 9.7 0 0 0 5.4-1.6",
  trash: "M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3",
  play: "M8 5v14l11-7z",
  backdrops: "M4 5h16v6H4zM6 14h12v5H6zM8 8h5M9 16.5h4",
  pause: "M8 5v14M16 5v14",
  rename: "M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4",
  crop: "M6 2v14a2 2 0 0 0 2 2h14M18 22V8a2 2 0 0 0-2-2H2",
  general: "M4 6h9M17 6h3M15 4v4M4 12h3M11 12h9M9 10v4M4 18h11M19 18h1M17 16v4",
});

const sceneById = (id) => draft.scenes.find((s) => s.id === id);
const isLinked = (name) => !!name && name.startsWith("@");
const pictureInfo = (name) => images.find((i) => i.name === name) || linked[name] || {};
const imageUrl = (name) => pictureInfo(name).url;
const thumbsMade = {};   // linked pictures' thumbnails made since the page loaded (keshikiThumbs)
const thumbUrl = (name) => pictureInfo(name).thumb || thumbsMade[name] || "";
const bg = (url) => (url ? { backgroundImage: `url("${url}")` } : {});
// Every picture a scene uses (in the draft: an unsaved scene's pictures count too).
const imagesInUse = () => new Set(draft.scenes.flatMap((sc) => sc.versions.map((v) => v.image)).filter(Boolean));
// A long folder path, shortened to its last two parts (the full path goes in a tooltip).
const shortPath = (path) => {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts.length > 2 ? `…${path.includes("\\") ? "\\" : "/"}${parts.slice(-2).join(path.includes("\\") ? "\\" : "/")}` : path;
};

function hhmm(minutes) {
  const m = ((Math.round(minutes) % 1440) + 1440) % 1440;
  return String(Math.floor(m / 60)).padStart(2, "0") + ":" + String(m % 60).padStart(2, "0");
}

function sceneThumb(scene) {
  const v = (scene.versions || []).find((v) => v.image);
  return v ? thumbUrl(v.image) : null;
}
const sceneImage = (scene) => ((scene.versions || []).find((v) => v.image) || {}).image || "";

// A picture's thumbnail as a background, marked with the picture: a linked folder's thumbnails
// are made in the background after the page has drawn, and keshikiThumbs fills them in. Until
// then the tile is empty (never the full picture: a folder of big ones would bog the page down).
const thumbOf = (name) => ({ style: bg(thumbUrl(name)), "data-thumb": name || "" });
window.keshikiThumbs = (made) => {
  Object.assign(thumbsMade, made);
  for (const el of document.querySelectorAll("[data-thumb]")) {
    const thumb = made[el.dataset.thumb];
    if (!thumb) continue;
    if (el.tagName === "IMG") el.src = thumb;
    else el.style.backgroundImage = `url("${thumb}")`;
  }
};

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

// Whether edits and chosen moments show in Anki's window too (the footer's switch, kept apart
// from the config: settings_page.py, preferences).
const inWindow = () => !S || S.in_window !== false;
const andWindow = () => (inWindow() ? "here and in Anki's window" : "here");

function refreshPreviews() {
  for (const box of document.querySelectorAll("[data-screen]")) {
    call("look", { cfg: draft, screen: box.dataset.screen }).then((look) => {
      stageFor(box).apply(look && !look.error ? Object.assign(look, { fade: 400 }) : null);
      if (box.contrast) box.contrast.soon(50);   // measured on the picture now showing
      box.querySelector(".mock-empty").hidden = !!(look && look.layers);
    });
  }
  const preview = document.querySelector(".preview");
  if (preview) updateScenePreview(preview, true);
  updateLightPreview();
  styleBackdropMock();
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
  const { main, study, done } = draft.screens;
  return [
    ...pageHead("Screens", "Choose backgrounds for each screen. Enable Preview below to see changes in Anki before saving."),
    screenCard("main", "Deck list", "Your decks, and while Anki starts",
      sceneChooser(main), lookControls(main), backdropSwitch(main)),
    screenCard("study", "Studying", "Overview, reviews and the finished screen",
      check(study.enabled, "Show a background while studying", (on) => { study.enabled = on; }),
      dependent(study.enabled,
        h("div", { className: "choices" },
          radio("source", study.same_as_main, "Same scenes as the deck list", () => { study.same_as_main = true; changed(true); }),
          radio("source", !study.same_as_main, "Choose different scenes", () => { study.same_as_main = false; changed(true); })),
        !study.same_as_main && sceneChooser(study),
        lookControls(study))),
    // Once every deck is done for today, these scenes take over both screens.
    screenCard("done", "All done for today", "Use these scenes on all screens when no cards remain.",
      check(done.enabled, "Use different scenes when finished", (on) => { done.enabled = on; }),
      dependent(done.enabled,
        sceneChooser(done),
        lookControls(done),
        backdropSwitch(done),
        h("p", { className: "help" }, "Your usual scenes return when new cards become due."))),
  ];
}

// A deck-list screen uses the Backdrops page's settings, or Anki's own look. Configure leads
// there while they're on (the page is in the sidebar either way).
function backdropSwitch(screen) {
  const configure = h("button", { type: "button", className: "link", disabled: !screen.backdrops,
                                  title: "Set up backdrops on the Backdrops page",
                                  onclick: () => { page = "backdrops"; render(); } }, "Configure...");
  return h("div", { className: "field backdrop-switch" }, h("span", { className: "label" }, "Backdrops"),
    h("div", { className: "backdrop-line" },
      h("label", { className: "check" },
        h("input", { type: "checkbox", checked: !!screen.backdrops, onchange: (e) => {
          screen.backdrops = e.target.checked;
          configure.disabled = !e.target.checked;
          changed();
        } }), "Use backdrops"),
      configure));
}

// A screen: its preview on the left, what it shows on the right.
function screenCard(screen, title, sub, ...controls) {
  return h("section", { className: "panel screen-card", "data-card": screen },
    h("div", { className: "panel-head" }, h("h2", {}, title), h("span", { className: "help" }, sub)),
    h("div", { className: "screen-body" }, mock(screen), h("div", { className: "screen-controls" }, controls)));
}

function check(checked, label, set) {
  return h("label", { className: "check" },
    h("input", { type: "checkbox", checked, onchange: (e) => { set(e.target.checked); changed(true); } }), label);
}

// Controls that only matter while the checkbox above them is ticked: indented under it,
// and shown disabled (not hidden) while it isn't.
function dependent(enabled, ...kids) {
  return h("fieldset", { className: "dependent", disabled: !enabled }, kids);
}

function welcome() {
  return h("div", { className: "panel blank" },
    h("h2", {}, "Start with a picture"),
    h("p", {}, "Add a few images and they'll appear behind Anki's main window. Later you can turn them into scenes that follow the time of day or your progress through today's reviews."),
    h("button", { type: "button", className: "primary", onclick: () => addImagesAsScenes() }, "Add images..."));
}

function sceneChooser(screen) {
  const options = draft.scenes.filter((s) => !screen.scenes.includes(s.id));
  const add = h("select", { "aria-label": "Add a scene", onchange: (e) => {
    if (e.target.value) { screen.scenes.push(e.target.value); changed(true); }
  } }, h("option", { value: "" }, screen.scenes.length ? "Add another..." : "Choose a scene..."),
     options.map((s) => h("option", { value: s.id }, s.name)));
  // The chosen scenes, then the dropdown for another under them; the label sits at the top.
  return [
    h("div", { className: "field scene-field" }, h("span", { className: "label" }, "Scenes"),
      h("div", { className: "scene-pick" }, screen.scenes.length > 0 && h("div", { className: "chips" },
        screen.scenes.map((id) => {
          const scene = sceneById(id);
          const thumb = sceneThumb(scene);
          return h("span", { className: "chip" },
            thumb ? h("img", { src: thumb, alt: "", "data-thumb": sceneImage(scene) })
              : h("span", { className: "swatch", "data-thumb": sceneImage(scene) }),
            h("span", { className: "chip-name", title: scene.name },
              scene.kind === "album" ? `${scene.name} (${albumPictures(scene).length})` : scene.name),
            h("button", { type: "button", "aria-label": `Remove ${scene.name}`, title: "Remove",
                          onclick: () => { screen.scenes = screen.scenes.filter((x) => x !== id); changed(true); } }, "×"));
        })),
        options.length ? add : null)),
    // A screen's scenes, and each picture of an album, take turns; with one there's nothing to shuffle.
    screenTurns(screen) > 1 && h("div", { className: "field" }, h("label", {}, "Shuffle every"),
      h("select", { className: "shuffle", onchange: (e) => { screen.every = Number(e.target.value); changed(); } },
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
  const singles = draft.scenes.filter((sc) => sc.kind === "single" && sc.versions[0] && sc.versions[0].image);
  return [
    ...pageHead("Scenes", "A scene is one picture, an album of pictures that take turns, or versions of one picture that change through the day."),
    h("div", { className: "scenes" },
      // Stays in view while the editor beside it scrolls.
      h("aside", { className: "scene-side" },
        h("div", { className: "list-actions", role: "group", "aria-labelledby": "newSceneLabel" },
          h("span", { className: "group-label", id: "newSceneLabel" }, "New scene"),
          h("button", { type: "button", id: "addImages", title: "One picture, or an album of several",
                        onclick: () => addImagesAsScenes() }, "From images..."),
          h("button", { type: "button", id: "addFolder", title: "An album of a folder's pictures",
                        onclick: () => askFolder() }, "From a folder..."),
          h("button", { type: "button", id: "addDay", title: "Versions of a picture that change through the day",
                        onclick: () => addScene("day") }, "Day cycle"),
          singles.length > 1 && h("button", { type: "button", id: "combine", title: "Put single pictures in one album",
                                              onclick: () => askCombine(singles) }, "Combine pictures...")),
        // In a narrow window, a dropdown in place of the list (CSS shows one or the other).
        h("label", { className: "scene-select" }, h("span", {}, "Scene"),
          h("select", { "aria-label": "Scene", onchange: (e) => { selectScene(e.target.value); render(); } },
            draft.scenes.map((s) => h("option", { value: s.id, selected: s.id === sel }, s.name)))),
        h("div", { className: "scene-list" }, draft.scenes.map((s) =>
          h("button", { type: "button", className: "scene-item", "aria-current": s.id === sel ? "true" : "false",
                        onclick: () => { selectScene(s.id); render(); } },
            h("span", { className: "thumb", ...thumbOf(sceneImage(s)) }),
            h("span", { className: "item-name", title: s.name }, s.name), h("small", {}, kindLabel(s))))),
        h("button", { type: "button", className: "link library-link", id: "openLibrary",
                      title: "Every picture you've added, which scenes use them, and the trash",
                      onclick: () => openLibrary() }, "Picture library & trash...")),
      scene ? sceneEditor(scene) : h("div", { className: "panel blank" }, h("p", {}, "Add images or start a day cycle to make your first scene.")))];
}

// Several pictures make an album (they take turns on a screen); one is a scene of its own.
// The deck list gets the new scene if it has nothing yet.
async function addImagesAsScenes() {
  const res = await call("import");
  if (!res || res.error || !res.added.length) return;
  images = res.images;
  const scene = await call("new_scene", res.added.length === 1
    ? { kind: "single", image: res.added[0] } : { kind: "album", images: res.added });
  draft.scenes.push(scene);
  if (!draft.screens.main.scenes.length) draft.screens.main.scenes.push(scene.id);
  selectScene(scene.id);
  changed(true);
}

// A folder becomes an album: linked (it keeps in step with the folder, rescanned when Anki
// starts and the settings open) or copied now (it stays as it is).
async function askFolder() {
  const path = await call("pick_folder");
  if (!path) return;
  let subfolders = true;
  let mode = "link";
  const count = h("p", { className: "help folder-count" });
  const error = h("p", { className: "error folder-error" });
  const go = h("button", { type: "button", className: "primary", id: "addFolderGo", disabled: true, onclick: async () => {
    go.disabled = true;
    const res = await call("add_folder", { path, subfolders, mode });
    if (!res || res.error) { error.textContent = (res && res.error) || "Couldn't add that folder."; go.disabled = false; return; }
    closeModal();
    if (res.images) images = res.images;
    Object.assign(linked, res.linked);
    draft.scenes.push(res.scene);
    if (!draft.screens.main.scenes.length) draft.screens.main.scenes.push(res.scene.id);
    selectScene(res.scene.id);
    page = "scenes";
    changed(true);
  } }, "Add");
  const recount = async () => {
    const res = await call("folder_info", { path, subfolders });
    const n = (res && res.count) || 0;
    count.textContent = res && res.error ? res.error : `${n} picture${n === 1 ? "" : "s"}`;
    go.disabled = !n;
  };
  openModal(h("div", { className: "dialog small folder-dialog" },
    h("h2", {}, "Add a folder"),
    h("p", { className: "folder-path", title: path }, shortPath(path)),
    h("label", { className: "check" },
      h("input", { type: "checkbox", id: "folderSubfolders", checked: subfolders,
                   onchange: (e) => { subfolders = e.target.checked; recount(); } }), "Include subfolders"),
    count,
    h("div", { className: "choices" },
      radio("folderMode", true, "Keep in step with the folder", () => { mode = "link"; }),
      h("p", { className: "help indent" }, "Pictures you add, change or remove there show up here the next time Anki starts or these settings open."),
      radio("folderMode", false, "Copy the pictures now", () => { mode = "copy"; }),
      h("p", { className: "help indent" }, "The album stays as it is, even if the folder changes or goes away.")),
    error,
    h("div", { className: "dialog-foot" }, h("button", { type: "button", onclick: closeModal }, "Cancel"), go)));
  recount();
}

// The picture library: each picture marked in use or not, and the trash, where unused
// pictures wait to be restored or deleted for good. Only pictures added to Keshiki: a linked
// folder's stay where they are, so its album can have more pictures than the library.
function openLibrary(tab = "library") {
  const tabs = h("div", { className: "tabs", role: "tablist" });
  const scope = h("p", { className: "help library-scope" },
    "Imported pictures only. Folder-linked pictures stay in their original folders.");
  const body = h("div", { className: "library-body" });
  const foot = h("div", { className: "dialog-foot" });
  const move = async (op, names) => {
    const res = await call(op, names);
    if (res.images) images = res.images;
    trashed = res.trash;
    draw();
  };
  const tile = (img, label, action, onclick) => h("div", { className: "lib-tile", title: img.name },
    h("span", { className: "lib-thumb", style: bg(img.thumb) }),
    label && h("span", { className: "lib-badge" + (label === "In use" ? "" : " quiet") }, label),
    action && h("button", { type: "button", className: "lib-action", onclick }, action));
  const tabButton = (id, text) => h("button", { type: "button", role: "tab", className: "tab", id: `tab-${id}`,
    "aria-selected": tab === id ? "true" : "false", onclick: () => { tab = id; draw(); } }, text);
  const draw = () => {
    tabs.replaceChildren(tabButton("library", `Library · ${images.length}`), tabButton("trash", `Trash · ${trashed.length}`));
    const done = h("button", { type: "button", className: "primary", onclick: closeModal }, "Done");
    // Nothing to show: a note in the middle. Actions with nothing to act on aren't shown.
    const empty = (text) => h("p", { className: "help empty-note" }, text);
    scope.hidden = tab !== "library" || !draft.scenes.some((sc) => sc.folder);
    if (tab === "library") {
      const used = imagesInUse();
      const unused = images.filter((img) => !used.has(img.name));
      body.replaceChildren(images.length
        ? h("div", { className: "grid library-grid" }, images.map((img) => used.has(img.name)
            ? tile(img, "In use") : tile(img, "Unused", "Move to trash", () => move("trash", [img.name]))))
        : empty("No pictures yet."));
      foot.replaceChildren(...[
        h("span", { className: "help foot-note" }, unused.length ? `${unused.length} not used by any scene`
          : images.length === 1 ? "The picture is used by a scene."
          : images.length ? `All ${images.length} pictures are used by scenes.` : ""),
        unused.length > 0 && h("button", { type: "button", id: "trashUnused",
                                           onclick: () => move("trash", unused.map((img) => img.name)) },
          `Move ${unused.length} unused to trash`),
        done].filter(Boolean));
    } else {
      body.replaceChildren(trashed.length
        ? h("div", { className: "grid library-grid" }, trashed.map((img) => tile(img, null, "Restore", () => move("restore", [img.name]))))
        : empty("The trash is empty."));
      foot.replaceChildren(...[
        h("span", { className: "help foot-note" }, trashed.length ? "Restored pictures go back to the library." : ""),
        trashed.length > 0 && h("button", { type: "button", id: "restoreAll",
                                            onclick: () => move("restore", trashed.map((img) => img.name)) }, "Restore all"),
        trashed.length > 0 && h("button", { type: "button", className: "danger", id: "emptyTrash", onclick: async () => {
          const ok = await confirmDialog({ title: `Delete ${trashed.length} picture${trashed.length === 1 ? "" : "s"} for good?`,
            yes: "Empty trash", danger: true, text: "They're deleted from Keshiki's picture folder and can't be brought back." });
          if (!ok) return;
          const res = await call("empty_trash");
          trashed = res.trash;
          draw();
        } }, "Empty trash"),
        done].filter(Boolean));
    }
  };
  openModal(h("div", { className: "dialog library-dialog" },
    h("div", { className: "dialog-head" }, h("h2", {}, "Picture library"), tabs), scope, body, foot));
  draw();
}

async function rescanFolder(scene) {
  const res = await call("rescan", scene.folder);
  if (!res) return;
  S.missing = S.missing.filter((id) => id !== scene.id);
  if (res.missing) S.missing.push(scene.id);
  else {
    Object.assign(linked, res.linked);
    scene.folder.hidden = res.hidden || [];
    scene.versions = res.images.map((image) => ({ label: "", image }));
    albumShown = Math.min(albumShown, Math.max(0, scene.versions.length - 1));
  }
  changed(true);
}

async function addImagesToAlbum(scene) {
  const res = await call("import");
  if (!res || res.error || !res.added.length) return;
  images = res.images;
  scene.versions.push(...res.added.map((image) => ({ label: "", image })));
  changed(true);
}

// Single-picture scenes folded into one album. A screen that showed any of them shows the
// album instead, where the first one was; their positions belong to the pictures, so they stay.
async function combineIntoAlbum(singles, name) {
  const album = await call("new_scene", { kind: "album", name, images: singles.map((sc) => sc.versions[0].image) });
  const ids = new Set(singles.map((sc) => sc.id));
  for (const screen of Object.values(draft.screens)) {
    const at = screen.scenes.findIndex((id) => ids.has(id));
    if (at < 0) continue;
    screen.scenes = screen.scenes.filter((id) => !ids.has(id));
    screen.scenes.splice(at, 0, album.id);
  }
  draft.scenes = draft.scenes.filter((sc) => !ids.has(sc.id));
  draft.scenes.push(album);
  selectScene(album.id);
  changed(true);
}

// Which single pictures to combine, all ticked to start, and the album's name.
function askCombine(singles) {
  const picked = new Set(singles.map((sc) => sc.id));
  const name = h("input", { type: "text", className: "album-name", value: "Album", "aria-label": "Album name" });
  const go = h("button", { type: "button", className: "primary", id: "combineGo", onclick: () => {
    closeModal();
    combineIntoAlbum(singles.filter((sc) => picked.has(sc.id)), name.value.trim() || "Album");
  } });
  const count = () => {
    go.textContent = `Combine ${picked.size} pictures`;
    go.disabled = picked.size < 2;
  };
  openModal(h("div", { className: "dialog small combine-dialog" },
    h("h2", {}, "Combine into an album"),
    h("p", { className: "help" }, "The pictures become one album; screens that showed them show the album, and its pictures take turns."),
    h("div", { className: "field" }, h("label", {}, "Album name"), name),
    h("div", { className: "combine-list" }, singles.map((sc) => h("label", { className: "check" },
      h("input", { type: "checkbox", checked: true, onchange: (e) => { e.target.checked ? picked.add(sc.id) : picked.delete(sc.id); count(); } }),
      h("span", { className: "thumb", ...thumbOf(sceneImage(sc)) }), sc.name))),
    h("div", { className: "dialog-foot" }, h("button", { type: "button", onclick: closeModal }, "Cancel"), go)));
  count();
}

// Open a scene in the editor (or none): it starts at now, and a moment scrubbed in the scene
// before stops showing in Anki's main window.
function selectScene(id) {
  stopPlaying();
  if (scrub !== null) call("end_moment");
  sel = id;
  scrub = null;
  albumShown = 0;
  albumFollow = true;
}

async function addScene(kind) {
  const scene = await call("new_scene", { kind });
  draft.scenes.push(scene);
  selectScene(scene.id);
  page = "scenes";
  changed(true);
}

async function deleteScene(scene) {
  const ok = await confirmDialog({ title: `Delete "${scene.name}"?`, yes: "Delete scene", danger: true,
    text: "It comes off every screen that shows it; its pictures stay. Until you save, Cancel brings it back." });
  if (!ok) return;
  selectScene(null);
  draft.scenes = draft.scenes.filter((s) => s !== scene);
  for (const screen of Object.values(draft.screens)) screen.scenes = screen.scenes.filter((id) => id !== scene.id);
  changed(true);
}

function sceneEditor(scene) {
  pausePlaying();   // a redraw keeps the run; play carries on with it
  const preview = h("div", { className: "preview" },
    h("span", { className: "readout" }),
    timed(scene) && h("div", { className: "preview-controls" },
      h("button", { type: "button", id: "backToNow", hidden: scrub === null,
                    title: `Stop previewing this moment, ${andWindow()}`,
                    onclick: () => { stopPlaying(); scrub = null; updateScenePreview(preview, false); } }, "Back to now"),
      h("select", { id: "playSpeed", "aria-label": "Timelapse length",
                    title: scene.kind === "day" ? "Timelapse: how long the whole day takes to play"
                                                : "Timelapse: how long a whole session takes to play",
                    onchange: (e) => {
                      playSeconds = Number(e.target.value);
                      if (playing) { pausePlaying(); play(scene, preview); }   // carry on at the new speed
                    } },
        PLAY_SPEEDS.map(([secs, label]) => h("option", { value: secs, selected: secs === playSeconds },
          `${scene.kind === "day" ? "24 h" : "All"} in ${label}`))),
      h("button", { type: "button", className: "play", id: "play", "aria-label": "Play",
        title: scene.kind === "day" ? `Play the next 24 hours, ${andWindow()}`
                                    : `Play on to finished, ${andWindow()}`,
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
      h("span", { className: "kind" }, kindLabel(scene)),
      h("button", { type: "button", className: "danger", id: "deleteScene", onclick: () => deleteScene(scene) },
        icon("trash"), "Delete scene")),
    scene.kind === "album" ? null : preview);   // an album's is in its stage (albumGrid)
  if (timed(scene)) panel.append(ribbon(scene, preview));
  panel.append(versionTable(scene, preview));
  return panel;
}

// One line per version: picture, name, when it starts, how long it fades in.
// Day cycles and progress scenes change with the clock or today's reviews; they have a timeline.
const timed = (scene) => scene.kind === "day" || scene.kind === "progress";

// An album's pictures as tiles: clicking one shows it in the preview and opens the picker
// (to place or replace it), × takes it out, and the last tile adds more.
let albumShown = 0;
// A newly opened album starts on the picture Anki's window shows now (albumGrid, showing).
let albumFollow = false;
const SCREEN_NAMES = { main: "the deck list", study: "while studying" };

function albumGrid(scene, preview) {
  const folder = scene.folder;
  let showing = {};   // picture index -> the screens showing it now
  const select = (i) => {
    albumShown = i;
    tiles.forEach((t, j) => t.classList.toggle("shown", j === i));
    updateScenePreview(preview, false);
    drawNow();
  };
  const tiles = scene.versions.map((v, i) => h("div", { className: "album-tile" + (i === albumShown ? " shown" : "") },
    h("button", { type: "button", className: "pick" + (v.image ? "" : " empty"), ...thumbOf(v.image),
                  title: v.image, "aria-label": `Preview ${v.image}`,
                  onclick: () => {
                    albumFollow = false;   // chosen here: the picture showing now doesn't take over
                    if (v.image) select(i);
                    else pickImage(v.image, (name) => { v.image = name; changed(true); });
                  } },
      v.image ? "" : "+"),
    // A linked album only hides a picture (it stays in the folder); another takes it out
    // (it stays in the picture library). Neither deletes anything.
    h("button", { type: "button", className: "icon-only remove" + (folder ? " hide" : ""),
                  title: folder ? "Hide picture" : "Remove from album",
                  "aria-label": `${folder ? "Hide" : "Remove"} ${v.image}`,
                  onclick: () => {
                    if (folder) folder.hidden = [...(folder.hidden || []), v.image];
                    scene.versions.splice(i, 1);
                    albumShown = Math.max(0, Math.min(albumShown, scene.versions.length - 1));
                    changed(true);
                  } }, icon(folder ? "hide" : "close"))));
  // Show the picture in the preview on Anki's window now, until its screen's shuffle moves on.
  const onScreen = albumOnScreen(scene);
  const nowButton = h("button", { type: "button", id: "showNow", onclick: async () => {
    nowButton.disabled = true;
    mark(await call("show_now", { scene: scene.id, image: scene.versions[albumShown].image, cfg: draft }));
  } }, "Show in Anki now");
  const cropButton = h("button", { type: "button", id: "adjustCrop", onclick: () => {
    const v = scene.versions[albumShown];
    if (v && v.image) pickImage(v.image, () => {}, null, -1, { positionOnly: true });
  } }, icon("crop"), "Adjust crop...");
  // Why Show in Anki now can't be used, when it can't: said beside it, where it stays put.
  const nowNote = h("span", { className: "help now-note" });
  const drawNow = () => {
    const screens = showing[albumShown];
    nowButton.disabled = !onScreen || !!screens;
    nowNote.textContent = !onScreen ? "To show it, use this album on a screen first (Screens page)."
      : screens ? `Showing now on ${screens.map((k) => SCREEN_NAMES[k]).join(" and ")}.`
      : "Until the album's next shuffle.";
    nowButton.title = !onScreen ? "This album isn't on any screen yet" : screens ? "Already showing" : "";
    cropButton.disabled = !(scene.versions[albumShown] || {}).image;
  };
  // Which picture each screen shows now: marked on its tile.
  const mark = (res) => {
    // An answer for tiles a redraw has replaced: the new ones asked for their own.
    if (!res || res.error || sceneById(sel) !== scene || !tiles.length || !tiles[0].isConnected) return;
    // By name: Anki's window may not have this page's latest numbering yet.
    showing = {};
    for (const [screen, shown] of Object.entries(res)) {
      const index = shown && shown.scene === scene.id ? scene.versions.findIndex((v) => v.image === shown.image) : -1;
      if (index >= 0) (showing[index] ||= []).push(screen);
    }
    tiles.forEach((t, i) => {
      t.querySelector(".now-badge")?.remove();
      if (showing[i]) t.append(h("span", { className: "now-badge", title: `Showing now on ${showing[i].map((k) => SCREEN_NAMES[k]).join(" and ")}` }, "Now"));
    });
    const first = Object.keys(showing)[0];
    if (albumFollow && first !== undefined && Number(first) !== albumShown) select(Number(first));
    albumFollow = false;
    drawNow();
  };
  call("showing", { cfg: draft }).then(mark);
  drawNow();
  return h("div", { className: "album-wrap" },
    folder && h("div", { className: "folder-line" },
      h("span", { className: "folder-path", title: folder.path }, shortPath(folder.path)),
      h("label", { className: "check" },
        h("input", { type: "checkbox", id: "albumSubfolders", checked: !!folder.subfolders,
                     onchange: (e) => { folder.subfolders = e.target.checked; rescanFolder(scene); } }), "Include subfolders"),
      h("button", { type: "button", className: "link", id: "rescan", onclick: () => rescanFolder(scene) }, "Rescan now"),
      // In the system's file manager: there's no opening a folder that can't be found.
      h("button", { type: "button", className: "link", id: "openAlbumFolder", title: folder.path,
                    disabled: (S.missing || []).includes(scene.id),
                    onclick: () => call("open_folder", { path: folder.path }) }, "Open folder")),
    folder && (S.missing || []).includes(scene.id)
      && h("p", { className: "error folder-missing" }, "Can't find this folder (moved, renamed, or a drive that isn't connected). Showing its last pictures."),
    folder
      ? help("Updates from this folder. Hidden pictures stay on disk.",
          "Pictures you add, change or remove in the folder show up here when Anki starts, when these settings open, "
          + "or on Rescan now. Hiding a picture takes it out of this album only. On a screen, the album's pictures "
          + "take turns with its other scenes, one each time its shuffle changes.")
      : help("On a screen, the album's pictures take turns with its other scenes, one each time its shuffle changes."),
    // The picture chosen below, and what to do with it: in view while the tiles scroll under it.
    h("div", { className: "album-stage" }, preview,
      h("div", { className: "album-actions" }, nowButton, cropButton, nowNote)),
    h("div", { className: "album" }, ...tiles,
      !folder && h("button", { type: "button", className: "album-add", onclick: () => addImagesToAlbum(scene) }, "+ Add images...")),
    // Hidden pictures (still in the folder), folded away: each can come back.
    folder && (folder.hidden || []).length > 0 && disclosure(`hidden:${scene.id}`, `Hidden pictures (${folder.hidden.length})`,
      h("div", { className: "hidden-row" }, folder.hidden.map((name) => h("div", { className: "hidden-tile", title: name },
        h("span", { className: "lib-thumb", ...thumbOf(name) }),
        h("button", { type: "button", className: "lib-action show", onclick: () => {
          folder.hidden = folder.hidden.filter((n) => n !== name);
          rescanFolder(scene);   // back in its place in the folder's order
        } }, "Show"))))));
}

// Whether a screen uses this album (the deck list, studying, or all done).
function albumOnScreen(scene) {
  const { main, study, done } = draft.screens;
  return main.scenes.includes(scene.id) || (done.enabled && done.scenes.includes(scene.id))
    || (study.enabled && !study.same_as_main && study.scenes.includes(scene.id));
}

function versionTable(scene, preview) {
  if (scene.kind === "album") return albumGrid(scene, preview);
  if (scene.kind === "single") {
    const v = scene.versions[0];
    return h("div", { className: "versions single" },
      pickButton(v), h("span", { className: "file" }, v.image || "No image yet"),
      h("button", { type: "button", onclick: () => pickImage(v.image, (name) => { v.image = name; changed(true); }) },
        v.image ? "Change image..." : "Choose image..."));
  }
  const day = scene.kind === "day";
  const table = h("div", { className: "versions" },
    h("div", { className: "vhead" }, h("span", { className: "c-name" }, "Version"),
      h("span", { className: "c-start" }, day ? "Transition starts" : "Starts at"),
      h("span", { className: "c-end" }, day ? "Transition ends" : "Fades in over")),
    scene.versions.map((v, i) => versionRow(scene, v, i, preview)));
  table.append(h("button", { type: "button", className: "add-version", onclick: () => {
    const last = scene.versions[scene.versions.length - 1] || {};
    // A new day version follows the last one: it starts as that one is fully in.
    scene.versions.push(day
      ? (scene.versions.length ? { label: "", image: "", anchor: "after", offset: 0, fade: 30 }
        : { label: "", image: "", anchor: "sun", direction: "setting", from: 0, to: -6 })
      : { label: "", image: "", at: Math.min(100, (Number(last.at) || 0) + 10), fade: 10 });
    renaming = { scene: scene.id, index: scene.versions.length - 1 };
    changed(true);
  } }, "+ Add version"));
  return table;
}

function pickButton(v, scene = null, index = -1) {
  return h("button", { type: "button", className: "pick" + (v.image ? "" : " empty"), ...thumbOf(v.image),
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

// The sun's named moments (Python's SUN_MOMENTS), fetched for the day settings they
// were worked out from.
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
// The dropdowns name the rule; today's time it gives goes on the line under them.
const half = (direction) => moments.filter((m) => m.direction === direction || (direction === "setting" && m.key === "noon"));
const momentValue = (direction, degrees) => `${direction}:${degrees}`;
function momentOption(m, direction, selected) {
  return h("option", { value: momentValue(direction, m.degrees), selected }, m.name);
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
  // Two cells, each a small stack: under Transition starts, the rule (and a wait, or a set
  // time); under Transition ends, the rule or the length; and under each, today's time.
  let starts, fade;
  if (scene.kind === "day") {
    const clock = v.anchor === "clock";
    // "after": starts when the version above is fully in, plus a delay (v.offset); not for the first row.
    const above = i > 0 ? scene.versions[i - 1] : null;
    const follows = v.anchor === "after" && !!above;
    const sun = !clock && !follows;
    const direction = v.direction || "rising";
    const from = Number(v.from), to = Number(v.to);
    // Later in its half of the day: higher in the morning, lower in the evening (noon starts the evening).
    const after = (m) => (direction === "rising" ? m.degrees > from : m.key !== "noon" && m.degrees < from);
    const rule = h("select", { "aria-label": "Transition starts", onchange: (e) => {
        const mark = (S.marks || []).find((m) => m.index === i);
        if (e.target.value === "clock") {
          // Keep today's times when moving from the sun to the clock.
          Object.assign(v, { anchor: "clock", offset: Math.round(mark ? mark.start : 0), fade: Math.round(mark ? mark.fade : 30) });
          delete v.direction; delete v.from; delete v.to;
        } else if (e.target.value === "after") {
          // Keep today's times too: the wait is the gap there is now (none if it starts before).
          const prev = (S.marks || []).find((m) => m.index === i - 1);
          const gap = prev && mark ? (((mark.start - prev.start - prev.fade) % 1440) + 1440) % 1440 : 0;
          Object.assign(v, { anchor: "after", offset: Math.round(gap <= 720 ? gap : 0), fade: Math.round(mark ? mark.fade : 30) });
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
          momentOption(m, "rising", sun && direction === "rising" && m.degrees === from))),
        h("optgroup", { label: "Evening" }, half("setting").map((m) =>
          momentOption(m, "setting", sun && direction === "setting" && m.degrees === from))),
        sun && moments.length > 0 && !isMoment(direction, from) && customOption(direction, from),
        above && h("option", { value: "after", selected: follows }, afterLabel(above.label)),
        h("option", { value: "clock", selected: clock }, "At a set time"));
    // No rebuild on the boxes' edits: each keeps its focus, and the times redraw on their own.
    const minutes = (key, label, set) => h("input", { type: "number", min: 0, max: 720, value: v[key] || 0, "aria-label": label,
                                                     onchange: (e) => { set(Math.max(0, Number(e.target.value) || 0)); changed(); } });
    starts = cell("Transition starts", "when-start", rule,
      clock && h("span", { className: "unit" }, "at", h("input", { type: "time", value: hhmm(v.offset), "aria-label": "Starts at",
        onchange: (e) => {
          if (!e.target.value) return;   // mid-edit, the box can be empty for a moment
          const [hh, mm] = e.target.value.split(":").map(Number);
          v.offset = hh * 60 + mm;
          changed();
        } })),
      follows && h("span", { className: "unit labelled wait" }, "Delay",
        h("span", { className: "unit" }, minutes("offset", "Delay in minutes", (n) => { v.offset = n; }), "min")));
    // A set time, or after the version above: the transition's length, and when it ends under it.
    fade = clock || follows
      ? cell("Transition duration", "when-end", h("span", { className: "unit" },
          minutes("fade", "Transition duration in minutes", (n) => { v.fade = n; }), "min"))
      : cell("Transition ends", "when-end", h("select", { "aria-label": "Transition ends", onchange: (e) => { v.to = Number(e.target.value.split(":")[1]); changed(true); } },
          half(direction).filter(after).map((m) => momentOption(m, direction, m.degrees === to)),
          moments.length > 0 && !isMoment(direction, to) && customOption(direction, to)));
    if (clock || follows) fade.classList.add("duration");
  } else {
    starts = cell("Starts at", null, num("at", 0, 100, "% done", "Starts at percent done"));
    fade = cell("Fades in over", null, num("fade", 0, 100, "%", "Fade-in percent"));
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
    h("div", { className: "vtitle" }, versionName(scene, v, i),
      h("button", { type: "button", className: "link preview-transition", title: "Play this transition in the preview",
                    "aria-label": `Preview the transition to ${v.label || "this version"}`,
                    onclick: () => previewTransition(scene, preview, i) }, icon("play"), "Preview")),
    starts, fade,
    h("button", { type: "button", className: "icon-only c-remove", title: "Remove version", "aria-label": "Remove version",
                  onclick: () => { scene.versions.splice(i, 1); changed(true); } }, icon("close")));
}

// A version's name, as a heading: Rename (or a click on it) turns it into a box, and Enter or
// leaving the box keeps the name (Escape, the old one). In place, without a rebuild, so a click
// elsewhere still lands. A new version opens with its box.
let renaming = null;   // {scene, index}: the version whose name is being edited
const afterLabel = (label) => (label ? `After ${label}${label.endsWith("s") ? "'" : "'s"} transition ends`
                                     : "After the previous transition ends");
function versionName(scene, v, i) {
  if (!(renaming && renaming.scene === scene.id && renaming.index === i)) {
    return h("button", { type: "button", className: "vname", title: "Rename", "aria-label": `Rename ${v.label || "version"}`,
                         onclick: (e) => {
                           renaming = { scene: scene.id, index: i };
                           e.currentTarget.replaceWith(versionName(scene, v, i));
                         } },
      h("span", { className: "vname-text" + (v.label ? "" : " unnamed") }, v.label || "Unnamed"), icon("rename"));
  }
  const was = v.label;
  // The row below may start "After <this>'s transition ends": its name follows as it's typed.
  const follow = () => {
    const next = document.querySelector(`.version[data-index="${i + 1}"] option[value="after"]`);
    if (next) next.textContent = afterLabel(v.label);
  };
  // A rebuild while renaming makes a new box (renaming.input): the old one, gone, keeps out of it.
  const finish = (keep) => {
    if (!renaming || renaming.input !== input) return;
    renaming = null;
    v.label = keep ? input.value.trim() : was;
    follow();
    if (input.isConnected) input.replaceWith(versionName(scene, v, i));
    if (v.label !== was) changed();
  };
  const input = h("input", { type: "text", className: "label", value: v.label, placeholder: "Name", "aria-label": "Version name",
                             oninput: () => { v.label = input.value.trim(); follow(); },
                             onkeydown: (e) => {
                               if (e.key === "Enter") { e.preventDefault(); finish(true); }
                               else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); finish(false); }
                             },
                             onblur: () => finish(true) });
  renaming.input = input;
  requestAnimationFrame(() => { if (input.isConnected) { input.focus(); input.select(); } });
  return input;
}

// One of a version's two cells: its controls, stacked, and the time they make today (filled
// in from the preview's marks). The label shows only when the row is two lines (narrow).
function cell(label, when, ...controls) {
  return h("div", { className: "cell " + (when === "when-end" ? "c-end" : "c-start") },
    h("span", { className: "cell-label" }, label), controls, when && h("small", { className: "when " + when }));
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
  // A version's transition (previewTransition) takes its own time, and stays where it ends.
  const perMs = run.perMs || span / (playSeconds * 1000);
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
      scrub = done && day && !run.perMs ? null : day ? ((run.pos % 1440) + 1440) % 1440 : Math.min(run.pos, 100);
      updateScenePreview(preview, false).then(() => { busy = false; });
    }
    if (done) { run = null; pausePlaying(); }
    else playing.frame = requestAnimationFrame(step);
  };
  playing.frame = requestAnimationFrame(step);
}

// One version's transition, in the preview: brought into view, and played from a little before
// it starts to when it's fully in, in a few seconds (however long the transition is).
const TRANSITION_PLAY_MS = 4000;
function previewTransition(scene, preview, i) {
  const v = scene.versions[i];
  let from, to;
  if (scene.kind === "day") {
    const mark = (S.marks || []).find((m) => m.index === i);
    if (!mark) return;
    const lead = Math.min(20, Math.max(5, mark.fade / 4));
    from = mark.start - lead;
    to = mark.start + mark.fade + lead;
  } else {
    from = Math.max(0, Number(v.at) || 0);
    to = Math.min(100, from + (Number(v.fade) || 0) + 2);
    from = Math.max(0, from - 2);
  }
  stopPlaying();
  preview.scrollIntoView({ behavior: "smooth", block: "start" });
  run = { pos: from, end: to, perMs: (to - from) / TRANSITION_PLAY_MS };
  play(scene, preview);
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
    ? `Play the next 24 hours, ${andWindow()}` : `Play on to finished, ${andWindow()}`;
}

// The ribbon: each version's image along the axis, fading in where its fade runs.
function ribbon(scene, preview) {
  const day = scene.kind === "day";
  const span = day ? 1440 : 100;
  const box = h("div", { className: "ribbon" });
  const ticks = h("div", { className: "ticks" });
  const hand = h("div", { className: "hand" });
  // Where the pointer is, and the time there: click or drag to see it.
  const ghost = h("div", { className: "ghost", hidden: true }, h("span"));
  const input = h("input", { type: "range", min: 0, max: span, step: day ? 5 : 1, "aria-label": day ? "Time of day" : "Percent done",
                             title: day ? "Click or drag to see a time of day" : "Click or drag to see a point in the session",
                             oninput: (e) => { stopPlaying(); scrub = Number(e.target.value); updateScenePreview(preview, false); },
                             onpointermove: (e) => {
                               const r = box.getBoundingClientRect();
                               const at = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
                               ghost.hidden = false;
                               ghost.style.left = 100 * at + "%";
                               ghost.classList.toggle("flip", at > 0.9);
                               ghost.firstChild.textContent = day ? hhmm(at * 1440) : `${Math.round(at * 100)}%`;
                             },
                             onpointerleave: () => { ghost.hidden = true; } });
  box.append(ghost, hand, input);
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
    const seg = h("div", { className: "seg", "data-thumb": image, style: Object.assign(bg(thumbUrl(image)), {
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

// A day cycle's times in its order, from its first version's start today: each version
// starts at the first such time after the one above's start, so the times run on past midnight
// (minutes from today's midnight; 1440 and on is the next day). [[index, start, end]].
function cycleTimes(marks) {
  let last = null;
  return marks.slice().sort((a, b) => a.index - b.index).map((m) => {
    let start = ((m.start % 1440) + 1440) % 1440;
    if (last !== null) while (start < last) start += 1440;
    last = start;
    return [m.index, start, start + m.fade];
  });
}
const dayAndTime = (minutes) => `${minutes >= 1440 ? "Next day" : "Today"}, ${hhmm(minutes)}`;

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
  readout.textContent = (scrub === null ? "Now, " : "Preview, ") + (scene.kind === "day" ? hhmm(position)
    : position >= 100 ? "finished" : `${Math.round(position)}% done`);
  readout.hidden = !timed(scene);
  const back = document.getElementById("backToNow");
  if (back) back.hidden = scrub === null;
  // A chosen moment shows in Anki's window too; back to now hands it back to the screen's own look.
  // While playing, each step eases into the next instead of jumping.
  const ease = playing ? 160 : 0;
  const shown = scene.kind !== "album" ? scene
    : { ...scene, kind: "single", versions: scene.versions.slice(albumShown, albumShown + 1) };
  return call("compose", { scene: shown, day: draft.day, light: draft.light, position, images: draft.images,
                           show: timed(scene) && scrub !== null, cfg: draft, fade: ease }).then((res) => {
    // A late answer for a scene no longer on screen changes nothing.
    if (!res || res.error || sceneById(sel) !== scene || !preview.isConnected) return;
    S.anchors = res.anchors;
    S.marks = res.marks;
    stageFor(preview).apply({ layers: res.layers, light: res.light, dim: 0, blur: 0, fade: redrawRibbon ? 300 : ease },
                            !redrawRibbon && !ease);
    if (scene.kind === "day") {
      for (const [index, start, end] of cycleTimes(res.marks)) {
        const row = document.querySelector(`.version[data-index="${index}"]`);
        if (!row) continue;
        // Under a duration, the start and end it makes say which: "Starts next day, 00:41",
        // "Ends next day, 02:11" (under the dropdowns, the column heads do).
        const said = (word, minutes) => word + " " + dayAndTime(minutes).replace(/^\w/, (c) => c.toLowerCase());
        const duration = !!row.querySelector(".c-end.duration");
        row.querySelector(".when-start").textContent = duration ? said("Starts", start) : dayAndTime(start);
        row.querySelector(".when-end").textContent = duration ? said("Ends", end) : dayAndTime(end);
      }
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
function pickImage(current, use, scene = null, index = -1, { positionOnly = false } = {}) {
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
        used || isLinked(chosen) ? h("span", { className: "muted" }, "Used by a scene")
          : h("button", { type: "button", className: "link", id: "trashImage",
                          title: "Pictures → Trash brings it back, or deletes it for good", onclick: async () => {
              const res = await call("trash", [chosen]);
              images = res.images;
              trashed = res.trash;
              chosen = images[0] ? images[0].name : null;
              drawGrid(); drawSide();
            } }, "Move to trash")));
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

  if (positionOnly) {
    openModal(h("div", { className: "dialog position-dialog" },
      h("div", { className: "dialog-head" }, h("h2", {}, "The part that stays in view")),
      side,
      h("div", { className: "dialog-foot" }, h("button", { type: "button", className: "primary", onclick: closeModal }, "Done"))));
    drawSide();
    return;
  }
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

// -- Backdrops page ---------------------------------------------------------

// How the deck list stands off the picture, on the screens that use backdrops: the panel
// behind the decks, a panel behind the statistics under it, and outlines on the text.
// The preview is the deck list's scene with a stand-in for the statistics; it stays in view
// while the cards scroll, and the card under the pointer (or focus) marks its part of it.
function backdropsPage() {
  const b = draft.backdrops;
  const using = ["main", "done"].filter((k) => draft.screens[k].backdrops)
    .map((k) => (k === "main" ? "Deck list" : "All done for today"));
  const preview = mock("main");
  preview.classList.add("backdrop-mock");
  preview.append(h("div", { className: "mock-addon" },
    h("div", {}, "Studied 255 cards in 72 minutes today"),
    h("div", { className: "mock-stats" }, [["Past week", "9.4 hrs"], ["Total", "807 hrs"], ["Streak", "869 days"]]
      .map(([k, v]) => h("span", {}, k, h("b", {}, v)))),
    h("div", { className: "mock-heat" }, Array.from({ length: 52 }, (_, i) => h("i", { style: { opacity: String(0.35 + ((i * 37) % 13) / 20) } })))));
  const card = (target, title, sub, ...kids) => previewTarget(h("section", { className: "panel aligned" },
    h("div", { className: "panel-head" }, h("h2", {}, title), h("span", { className: "help" }, sub)), kids), target);
  return [
    ...pageHead("Backdrops", "Adjust the panels and text outlines that keep your deck list readable over backgrounds."),
    h("p", { className: "page-status" + (using.length ? " on" : "") },
      h("span", { className: "status-dot" }),
      using.length ? `In use on: ${using.join(", ")}` : "Not in use on any screen",
      h("button", { type: "button", className: "link", id: "manageScreens", title: "Each screen turns backdrops on with Use backdrops",
                    onclick: () => { page = "screens"; render(); } }, "Manage screens")),
    h("section", { className: "panel backdrop-preview" }, preview),
    card("table", "Deck list panel", "The panel behind your decks",
      slider("Opacity", b.table.opacity, 0, 90, "%", (v) => { b.table.opacity = v; }),
      slider("Background blur", b.table.frost, 0, 20, "px", (v) => { b.table.frost = v; }),
      note(help("Anki's default opacity is 40%. Background blur softens the image behind the panel."))),
    card("addon", "Statistics panel", "Anki's \"Studied N cards\" line, Review Heatmap, Study Time Stats",
      check(b.panel.enabled, "Show a panel behind statistics", (on) => { b.panel.enabled = on; }),
      dependent(b.panel.enabled,
        slider("Opacity", b.panel.opacity, 0, 90, "%", (v) => { b.panel.opacity = v; }),
        slider("Background blur", b.panel.frost, 0, 20, "px", (v) => { b.panel.frost = v; }),
        slider("Padding", b.panel.padding, 0, 40, "px", (v) => { b.panel.padding = v; }),
        colorField("Color source", b.panel, "color", "--canvas-elevated"),
        note(help("It fits around the statistics, and follows them as the page changes.")))),
    card("text", "Text readability", "Applies to all deck-list text, including text inside panels.",
      h("div", { className: "field" }, h("label", {}, "Text outline"),
        h("select", { className: "text-outline", onchange: (e) => { b.text.outline = e.target.value; changed(true); } },
          [["off", "Off"], ["needed", "Where needed"], ["everywhere", "Everywhere"]].map(([v, label]) =>
            h("option", { value: v, selected: b.text.outline === v }, label)))),
      dependent(b.text.outline !== "off",
        slider("Strength", b.text.strength, 0, 100, "%", (v) => { b.text.strength = v; })),
      note(help("Automatically adds an outline where the background reduces contrast.",
        "Where needed outlines only text the background makes hard to read. Everywhere outlines all of it, and "
        + "more where needed. The outline is always the text's opposite: dark behind light text. Keshiki works out "
        + "the color behind each piece of text from the picture it draws, with the panel it's on, and compares the "
        + "two as WCAG contrast ratios do (4.5:1 reads well). Text short of that is helped as much as it's short: "
        + "colored text first moves a little lighter (darker in a light theme) and its hue a touch away from the "
        + "picture's, then an outline makes up the rest. Anki's faint zero counts stay faint. It's measured again "
        + "when the scene, the page or the window changes."))),
  ];
}

// Help under a card's controls, in the controls' column.
const note = (...kids) => h("div", { className: "field" }, h("span"), h("div", {}, kids));

// A card that marks its part of the backdrop preview (the deck list panel, the statistics
// panel, the text) while the pointer is over it or focus is in it.
function previewTarget(section, target) {
  const update = () => {
    const box = document.querySelector(".backdrop-mock");
    if (box) box.classList.toggle(`mark-${target}`, section.isConnected
      && (section.matches(":hover") || section.contains(document.activeElement)));
  };
  // After the event, so focus has moved.
  for (const type of ["mouseenter", "mouseleave", "focusin", "focusout"]) section.addEventListener(type, () => setTimeout(update));
  return section;
}

// A color: the window's (theme), or one picked; the picker shows only for a custom one.
function colorField(label, obj, key, themeVar) {
  const theme = getComputedStyle(document.documentElement).getPropertyValue(themeVar).trim();
  const custom = !!obj[key];
  const picker = h("input", { type: "color", value: obj[key] || (/^#[0-9a-f]{6}$/i.test(theme) ? theme : "#2c2c2c"),
                              hidden: !custom, "aria-label": "Custom color",
                              oninput: (e) => { obj[key] = e.target.value; changed(); } });
  return h("div", { className: "field" }, h("label", {}, label),
    h("div", { className: "color-choice" },
      h("select", { "aria-label": label, onchange: (e) => { obj[key] = e.target.value === "custom" ? picker.value : ""; changed(true); } },
        h("option", { value: "", selected: !custom }, "Window color"),
        h("option", { value: "custom", selected: custom }, "Custom color")),
      picker));
}

// The preview takes the settings as they are now (as the main window does).
function styleBackdropMock() {
  const box = document.querySelector(".backdrop-mock");
  if (!box) return;
  const { table, panel, text } = draft.backdrops;
  const vars = {
    "--kk-table": table.opacity + "%", "--kk-table-frost": table.frost + "px",
    "--kk-panel": panel.opacity + "%", "--kk-panel-frost": panel.frost + "px", "--kk-pad": panel.padding + "px",
    "--kk-panel-color": panel.color || "var(--canvas-elevated)",
  };
  for (const [k, v] of Object.entries(vars)) box.style.setProperty(k, v);
  box.classList.toggle("paneled", !!panel.enabled);
  // The text help, as Anki's window has it (layers.js, Contrast), measured on the preview.
  if (!box.contrast) box.contrast = new keshiki.Contrast(box, stageFor(box));
  box.contrast.set(text);
}

// -- Day & time page -----------------------------------------------------

// The location's details (coordinates, fallback times) open with Change, and on their own
// while there's no location yet.
let editLocation = false;

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
  const known = day.latitude != null && day.longitude != null;
  const editing = editLocation || !known;
  const today = h("span", { className: "sun-today" });
  if (loc && known) {
    call("sun", day).then((t) => {
      today.textContent = t ? `Sunrise ${hhmm(t.sunrise)} · Sunset ${hhmm(t.sunset)}`
        : "The sun doesn't rise or set here today, so the fallback times stand in.";
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
  const findButton = (text, primary) => h("button", { type: "button", id: "locate", className: primary ? "primary" : "",
                                                      disabled: locating, onclick: locate }, text);
  // The place, short (town and region), with the whole name on hover.
  const place = day.place ? day.place.split(",").map((part) => part.trim()).slice(0, 2).join(", ") : "";
  return [
    ...pageHead("Day & time", "Set the daily timing used by day-cycle scenes and lighting effects."),
    // Each choice's settings under it, indented alike.
    h("section", { className: "panel aligned day-panel" },
      h("h2", {}, "Sunrise and sunset"),
      h("div", { className: "choices" },
        radio("daysource", !loc, "Use fixed times", () => { day.source = "manual"; changed(true); }),
        !loc && h("div", { className: "option-body" },
          time("sunrise", "Sunrise"), time("sunset", "Sunset"),
          note(help("Make these your own day: if your morning starts at 9, set sunrise to 09:00."))),
        radio("daysource", loc, "Use my location", () => { day.source = "location"; changed(true); }),
        loc && h("div", { className: "option-body" },
          h("div", { className: "field" }, h("span", { className: "label" }, "Location"),
            h("div", { className: "locate" },
              h("span", { className: "place", title: day.place || "" }, locating ? "Finding your location..." : place ? `Near ${place}`
                : known ? `${day.latitude}, ${day.longitude}` : "Not set yet"),
              known
                ? h("button", { type: "button", id: "changeLocation", "aria-expanded": String(editing),
                                onclick: () => { editLocation = !editLocation; render(); } }, editLocation ? "Done" : "Change")
                : findButton("Find my location", true))),
          locateError && note(h("div", { className: "error" }, locateError)),
          known && h("div", { className: "field" }, h("span", { className: "label" }, "Today"), today),
          editing && h("div", { className: "location-edit" },
            known && note(findButton("Find again", false)),
            note(help("Find my location asks for a rough position, only when you click it.",
              "It looks up your internet address at ipapi.co. You can also type coordinates from any map app: "
              + "north and east are positive.")),
            coord("latitude", "Latitude", 90), coord("longitude", "Longitude", 180),
            time("sunrise", "Fallback sunrise"), time("sunset", "Fallback sunset"),
            note(help("For days the sun doesn't rise or set here.")))))),
    lightPanel(),
  ];
}

// -- General page ---------------------------------------------------------
// What applies to every screen and scene alike.

function generalPage() {
  return [
    ...pageHead("General", "Settings that apply to every screen and scene."),
    h("section", { className: "panel aligned general-panel" },
      h("h2", {}, "Transitions"),
      slider("Crossfade duration", draft.transition_seconds, 0, 10, " s", (v) => { draft.transition_seconds = v; }),
      note(help("Blend between backgrounds when switching screens or shuffling scenes.",
        "Also when a scene or its settings change. A day-cycle scene moves between its versions at its own pace "
        + "instead: the transition times set for each version on the Scenes page."))),
    // Every screen's pictures: big ones from a copy sized for the screen (display.py).
    h("section", { className: "panel performance" },
      h("h2", {}, "Performance"),
      check(!!draft.display_copies, "Optimize large backgrounds", (on) => { draft.display_copies = on; }),
      help("Use smaller copies of large images to improve performance. Unblurred backgrounds may look slightly softer.",
        "Blurred backgrounds always use smaller copies, the more blur the smaller: the blur hides the difference. "
        + "The previews here always use copies too. Copies are kept in the add-on's user_files/display folder, up to "
        + "1 GB, and your pictures are never changed. Animated pictures are always shown as they are."),
      // Anki's own setting (Preferences > Appearance), which the add-on can't change for you.
      h("p", { className: "help video-driver" }, "Seeing lag or stuttering? Try Anki's Tools > Preferences > Appearance > "
        + "Video driver: OpenGL, then restart Anki.")),
  ];
}

// Daily lighting: lighting the pictures by the sun, with a strength and a bloom. A small
// preview shows one of your pictures in that light at a time picked on the day's strip (now,
// to start); a picked time shows in Anki's window too, until Back to now or leaving the page.
let lightAt = null;

function lightPanel() {
  const l = draft.light;
  const strip = h("div", { className: "daylight" });
  const ticks = h("div", { className: "ticks" });
  const hand = h("div", { className: "hand" });
  const minute = () => (lightAt === null ? new Date().getHours() * 60 + new Date().getMinutes() : lightAt);
  // Where the pointer is on the strip, and the time there.
  const ghost = h("div", { className: "ghost", hidden: true }, h("span"));
  const input = h("input", { type: "range", min: 0, max: 1440, step: 5, value: minute(), "aria-label": "Preview time",
                             title: "Click or drag to preview the light at another time",
                             oninput: (e) => { lightAt = Number(e.target.value); placeHand(); updateLightPreview(); },
                             onpointermove: (e) => {
                               const r = input.getBoundingClientRect();
                               const at = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
                               ghost.hidden = false;
                               ghost.style.left = 100 * at + "%";
                               ghost.classList.toggle("flip", at > 0.9);
                               ghost.firstChild.textContent = hhmm(at * 1440);
                             },
                             onpointerleave: () => { ghost.hidden = true; } });
  const now = h("button", { type: "button", className: "link", id: "lightNow", hidden: lightAt === null,
                            title: `Stop previewing this time, ${andWindow()}`,
                            onclick: () => { lightAt = null; call("end_moment"); placeHand(); updateLightPreview(); } }, "Back to now");
  const placeHand = () => { hand.style.left = (100 * minute()) / 1440 + "%"; now.hidden = lightAt === null; };
  placeHand();
  const drawStrip = () => call("daylight", { day: draft.day, strength: l.tint_strength }).then((res) => {
      if (!res || res.error) return;
      // A light gray wall through today, under the light at this strength.
      const n = res.samples.length - 1;
      strip.style.background = `linear-gradient(to right, ${res.samples.map((c, i) => `${c} ${((100 * i) / n).toFixed(2)}%`).join(", ")})`;
      const pct = (m) => (100 * m) / 1440 + "%";
      ticks.replaceChildren(h("span", { style: { left: "0%" } }, "00:00"),
        h("span", { className: "sun", style: { left: pct(res.anchors.sunrise) } }, "Sunrise " + hhmm(res.anchors.sunrise)),
        h("span", { className: "sun", style: { left: pct(res.anchors.sunset) } }, "Sunset " + hhmm(res.anchors.sunset)),
        h("span", { style: { left: "100%" } }, "24:00"));
  });
  drawStrip();
  const look = lightScene() && h("div", { className: "light-preview" }, h("span", { className: "readout" }));
  return h("section", { className: "panel aligned day-panel" },
    h("h2", {}, "Daily lighting"),
    check(l.tint, "Adjust lighting throughout the day", (on) => { l.tint = on; }),
    h("div", { className: "indent-help" },
      help("Warm at sunrise and sunset, blue at twilight, dim at night.",
        "Plain light at midday; the night is dim and faded, the way eyes see in the dark. It follows the sun's height: "
        + "for your location, or the sunrise and sunset times above. It can light every scene, even a single "
        + "picture, or only day-cycle scenes, so other pictures keep their own colors all day.")),
    dependent(l.tint,
      h("div", { className: "light-body" + (look ? "" : " no-look") },
        look,
        h("div", { className: "light-controls" },
          h("div", { className: "field" }, h("span", { className: "label" }, "Applies to"),
            h("div", { className: "choices inline" },
              radio("lightScope", l.scope !== "all", "Day-cycle scenes only", () => { l.scope = "day"; changed(true); }),
              radio("lightScope", l.scope === "all", "All scenes", () => { l.scope = "all"; changed(true); }))),
          slider("Lighting strength", l.tint_strength, 0, 100, "%", (v) => { l.tint_strength = v; drawStrip(); }),
          h("div", { className: "field preview-time" }, h("span", { className: "label" }, "Preview time"),
            h("div", {}, h("div", { className: "daylight-wrap" }, strip, ghost, hand, input), ticks, now)),
          slider("Bloom", l.bloom, 0, 100, "%", (v) => { l.bloom = v; }),
          note(help("Adds a soft glow to lights in nighttime pictures.",
            "Only pictures that show night have it, and only after dark: their own lights (windows, lamps, stars) "
            + "stay a little brighter than the rest, and Bloom is the soft glow around them. Daytime pictures "
            + "and scenes daily lighting doesn't apply to have none."))))),
  );
}

// The picture the light preview uses: the deck list's first scene, or else the first scene
// (a day cycle shows its version for the chosen time; an album its first picture). Lighting
// only day cycles, it's the first day cycle, and there's no preview without one.
function lightScene() {
  const days = draft.light.scope !== "all";
  const scene = [...draft.screens.main.scenes.map(sceneById), ...draft.scenes]
    .find((sc) => sc && sc.versions.some((v) => v.image) && (!days || sc.kind === "day"));
  if (!scene) return null;
  return scene.kind === "album" ? { ...scene, kind: "single", versions: albumPictures(scene).slice(0, 1) } : scene;
}

function updateLightPreview() {
  // A chosen time: Anki's window shows its screen then, with the settings as they are now.
  if (lightAt !== null && page === "day") call("moment_at", { cfg: draft, minute: lightAt });
  const box = document.querySelector(".light-preview");
  const scene = lightScene();
  if (!box || !scene) return;
  const minute = lightAt === null ? new Date().getHours() * 60 + new Date().getMinutes() : lightAt;
  box.querySelector(".readout").textContent = (lightAt === null ? "Now, " : "Preview, ") + hhmm(minute);
  call("compose", { scene, day: draft.day, light: draft.light, images: draft.images, minute,
                    position: scene.kind === "day" ? minute : scene.kind === "progress" ? S.percent : 0 }).then((res) => {
    if (!res || res.error || !box.isConnected) return;
    stageFor(box).apply({ layers: res.layers, dim: 0, blur: 0, fade: 0 }, true);
  });
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
      // Dim, blur, shuffle and backdrops go back to defaults; which scenes show, and on which
      // screens, stays.
      restore: (d) => {
        for (const [key, screen] of Object.entries(d.screens)) {
          const kept = { scenes: screen.scenes };
          for (const k of ["same_as_main", "enabled"]) if (k in screen) kept[k] = screen[k];
          d.screens[key] = Object.assign(clone(S.defaults.screens[key]), kept);
        }
      },
      restoreLabel: "Reset adjustments",
      restoreTitle: "Dim, blur, shuffle and Use backdrops back to their defaults on every screen. Your scenes, and "
        + "which screens show them, stay. Nothing changes until Save.",
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
      id: "backdrops", title: "Backdrops", icon: "backdrops", render: backdropsPage,
      slice: (d) => d.backdrops,
      revert: (d) => { d.backdrops = clone(saved.backdrops); },
      restore: (d) => { d.backdrops = clone(S.defaults.backdrops); },
      restoreLabel: "Reset backdrop settings",
      restoreTitle: "The deck list panel, statistics panel and text outline back to their defaults. Nothing changes until Save.",
    },
    {
      id: "day", title: "Day & time", icon: "day", render: dayPage,
      slice: (d) => [d.day, d.light],
      revert: (d) => { d.day = clone(saved.day); d.light = clone(saved.light); },
      restoreLabel: "Reset Day & time settings",
      restoreTitle: "Sunrise and sunset, and light, back to their defaults. Nothing changes until Save.",
      restore: (d) => {
        d.day = clone(S.defaults.day);
        d.light = clone(S.defaults.light);
      },
    },
    {
      id: "general", title: "General", icon: "general", render: generalPage,
      slice: (d) => [d.transition_seconds, d.display_copies],
      revert: (d) => { d.transition_seconds = saved.transition_seconds; d.display_copies = saved.display_copies; },
      restoreLabel: "Reset general settings",
      restoreTitle: "Crossfade duration and Optimize large backgrounds back to their defaults. Nothing changes until Save.",
      restore: (d) => {
        d.transition_seconds = S.defaults.transition_seconds;
        d.display_copies = S.defaults.display_copies;
      },
    },
  ],
  // Whether unsaved edits show in Anki's window, beside the unsaved-changes status. A slow
  // computer can keep Anki's window out of it: it then changes only on Save.
  // The add-on's version above it, stacked (as Tsunagi has it).
  footer: () => h("div", { className: "about" },
    h("span", { id: "version", className: "addon-version" }),
    h("label", { className: "check in-window",
                 title: "Show unsaved edits, and moments you pick on a timeline, in Anki's main window as you make them" },
      h("input", { type: "checkbox", id: "in-window", checked: true, onchange: (e) => {
        S.in_window = e.target.checked;
        call("in_window", S.in_window).then(() => changed(true));   // sends the draft and moments again
      } }), "Preview in Anki's window")),
  onLoad: (state) => {
    document.getElementById("in-window").checked = state.in_window !== false;
    document.getElementById("version").textContent = state.version ? `Keshiki ${state.version}` : "";
    S.anchors = { sunrise: 390, sunset: 1170 };
    S.window = S.window || [16, 10];
    document.documentElement.style.setProperty("--kk-window", String(S.window[0] / S.window[1]));
    images = state.images;
    linked = state.linked || {};
    trashed = state.trash || [];
    S.missing = state.missing || [];
  },
  // Unsaved edits preview live in the main window (and in the page's own previews).
  onChange: (dirty) => {
    clearTimeout(pushTimer);
    pushTimer = setTimeout(() => {
      call("draft", dirty ? draft : null);
      refreshPreviews();
    }, 120);
  },
  beforeRender: (p) => {
    if (p !== "scenes") stopPlaying();
    if (p !== "day") lightAt = null;
    // A moment shown in Anki's window lasts while the page that chose it is showing: a day
    // cycle scrubbed on Scenes, a time picked on Day & time's light strip.
    if (!(p === "scenes" && scrub !== null) && !(p === "day" && lightAt !== null)) call("end_moment");
  },
  afterRender: () => refreshPreviews(),
  // kiso shots (dev): the Scenes page shows each scene in the editor, then the dialogs it opens.
  // Only looking: nothing is added, combined, trashed or saved.
  shots: {
    scenes: async ({ shot }) => {
      for (const s of draft.scenes.slice()) {
        selectScene(s.id);
        render();
        await shot(s.name);
      }
      if (!draft.scenes.length) await shot("Scenes");
      const combine = document.getElementById("combine");
      if (combine) {
        combine.click();
        await shot("Combine pictures");
        closeModal();
      }
      openLibrary();
      await shot("Picture library");
      document.getElementById("tab-trash").click();
      await shot("Trash");
      closeModal();
    },
    // Asked for by name (kiso shots --tour NAME --size WxH): the README's and listing's pictures.
    // The Screens page as most people see it: previewing in Anki's window, the default (only the
    // page is told so; the preference stays as it is).
    readme: async ({ shot }) => {
      const was = S.in_window;
      const box = document.getElementById("in-window");
      S.in_window = true;
      box.checked = true;
      page = "screens";
      render();
      await shot("Screens", { whole: false, wait: 1200 });
      S.in_window = was;
      box.checked = was !== false;
    },
    // The first day-cycle scene in the editor through a whole day, from 04:00 every half hour.
    "day-film": async ({ shot, wait }) => {
      const scene = draft.scenes.find((sc) => sc.kind === "day");
      if (!scene) throw new Error("no day-cycle scene");
      page = "scenes";
      selectScene(scene.id);
      render();
      await wait(1000);
      const preview = document.querySelector(".preview");
      for (let i = 0; i < 48; i++) {
        scrub = (240 + 30 * i) % 1440;
        await updateScenePreview(preview, false);
        await shot(hhmm(scrub), { whole: false, wait: 250 });
      }
      selectScene(scene.id);   // back to now, and Anki's window to its own look
      render();
    },
  },
  onCancel: () => stopPlaying(),
  onSaveError: (err) => { if (err.page === "scenes") sel = err.field; },
});
