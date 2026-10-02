# AnkiWeb listing

The text of Keshiki's AnkiWeb page, one section per field of AnkiWeb's upload form.
Kiso's AnkiWeb upload helper (a userscript) fills the form from this file and attaches the
latest release's `.ankiaddon`; without it, paste each section by hand.

## Title

A one-line description, under 80 characters; the words after the name are what people
search for. Anki's add-on list shows `manifest.json`'s name instead (a name packaged in the
file wins over AnkiWeb's title).

```text
🖼️ Keshiki - Background scenes that follow the sun
```

## Tags

Optional, space-separated. AnkiWeb keeps only the first 80 characters, spaces included.

```text
background wallpaper scenery theme day-night customization
```

## Support page

Optional; must start with `http`.

```text
https://github.com/mcgrizzz/Keshiki
```

## Branches

For the final branch's maximum, a `-` prefix (e.g. `-26.10.0`) blocks downloads on newer
Anki. Keep the minimum in step with `min_point_version` in `manifest.json`.

```text
Branch 1
Supports: [ 26.08.0 ] - [ 26.09.3 ]
```

## Description

Markdown and basic HTML. AnkiWeb joins lines into one paragraph, so separate the links with
blank lines. `{{version}}` and `{{release_url}}` are the release the helper attaches.

```markdown
Background scenes for Anki's main window that follow the sun through the day, and can change once you're done studying.

![A day-cycle scene at dawn, midday, dusk, night and midnight](https://raw.githubusercontent.com/mcgrizzz/Keshiki/main/docs/images/scenes-through-the-day.webp)

### Features

* **One picture across the whole window.** The toolbar, the deck list and the bottom bar show one continuous image, with no seams.
* **Day cycles.** Give a scene dawn, day, dusk and night versions. Each fades in between moments of the sun you choose (first light to sunrise, say), at a set time, or once the one before it is fully in, for the real sun where you are or the times you set.
* **Light by the sun.** Optionally colour any picture by the sun's height: warm low sun, plain midday, blue twilight and a dim night. At night a picture's own lights (lit windows, lamps, stars) stay lit and glow softly.
* **All done for today.** Different scenes once nothing is left to study in any deck.
* **Shuffle.** Put several scenes on a screen, or add a batch of pictures straight to it, and they take turns, every 15 minutes up to once a day. A screen with one scene keeps it.
* **Readable.** Dim and blur set separately for the deck list and for studying.

After installing, restart Anki and open **Tools → 🖼️ Keshiki**. Your location is only looked up if you click **Find my location**.

> Needs Anki 26.08 or newer. Turn off other background add-ons (like Custom Background Image and Gear Icon) while you use it.

[Source code and documentation](https://github.com/mcgrizzz/Keshiki)

[Report a problem](https://github.com/mcgrizzz/Keshiki/issues)

[What's new in {{version}}]({{release_url}})
```
