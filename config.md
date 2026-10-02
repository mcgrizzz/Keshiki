Open **Tools → 🖼️ Keshiki** (or this add-on's **Config** button) to change these settings. You don't need to edit the JSON by hand.

| Key | Meaning |
| --- | --- |
| `scenes` | Your scenes. `kind` is `single` or `day` (day cycle); `progress` scenes still work but can't be made in the settings for now. Each version has an `image` from `user_files/images`. A day version with `anchor` `sun` fades in as the sun, `direction` `rising` or `setting`, goes `from` one height `to` another, in degrees (0 is the horizon). With `anchor` `clock` it starts `offset` minutes after midnight and fades in over `fade` minutes. |
| `images` | For each image, the point kept in view when the window crops it: `{"x": 50, "y": 50}` in percent. |
| `screens.main` | The deck list: `scenes` (scene ids, shuffled when there are several), `every` (minutes per scene when shuffling; `0` picks one each time Anki starts), `dim` (0–90 percent) and `blur` (pixels). |
| `screens.study` | The deck overview, reviews and the finished screen. Same keys, plus `enabled`, and `same_as_main` to use the deck list's scenes. |
| `day` | Where sunrise and sunset come from: `source` `manual` uses `sunrise` and `sunset` (`HH:MM`); `location` uses `latitude` and `longitude`, with the typed times as a fallback. |
| `screens.done` | Once nothing is left to study in any deck: `enabled`, and the `scenes` (and `every`) both screens switch to. |
| `light` | `tint`: light the pictures by the sun's height, at `tint_strength` percent. At night, pictures that show night keep their own lights (found once, and kept beside the thumbnail), a little brighter and softly blooming. `scope`: `"all"` lights every scene, `"day"` only day cycles. |
| `transition_seconds` | How long the background takes to crossfade to a new picture. |
