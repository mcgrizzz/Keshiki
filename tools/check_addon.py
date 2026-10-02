"""Real-Anki check of the add-on plumbing: reload without a restart, and
turning Keshiki off and on in Tools > Add-ons."""

# isort: off
# kiso_dev.harness sets Qt up for offscreen use before aqt loads, so it comes first.
from kiso_dev.harness import addon, js, run, until

import aqt
from images import make_test_image
# isort: on


def background_on(app, web):
    return js(app, web, "!!(window.keshiki && keshiki.main && document.documentElement.classList.contains('keshiki-on'))")


def check(app, shots, base):
    mw = aqt.mw
    from keshiki.keshiki import library
    from keshiki.keshiki.config import migrate, new_scene

    name = library.import_files([str(make_test_image(base / "meadow.png", 120))])[0]
    cfg, _ = migrate({})
    scene = new_scene("single", image=name)
    cfg["scenes"] = [scene]
    cfg["screens"]["main"]["scenes"] = [scene["id"]]
    mw.addonManager.writeConfig("keshiki", cfg)
    addon().addon.feature.set_config(cfg)
    webs = [mw.toolbarWeb, mw.web, mw.bottomWeb]
    until(app, lambda: all(background_on(app, w) for w in webs), 10, "no background to start with")

    old = addon().addon.feature
    # Mark the pages: the reload redraws them, and the old ones already show a background.
    for web in webs:
        js(app, web, "window.kkBeforeReload = true")
    message = addon().reload_addon()
    assert message.startswith("reloaded"), message
    new = addon().addon.feature
    assert new is not old and old.subs._hooks == []
    until(app, lambda: all(not js(app, w, "!!window.kkBeforeReload") and background_on(app, w) for w in webs),
          10, "the pages weren't redrawn with a background after the reload")
    # Only the new renderer answers the hooks: one stage per page, not two.
    stages = "document.querySelectorAll('.keshiki-stage').length"
    until(app, lambda: js(app, mw.web, stages) == 1, 5,
          f"one stage per page after the reload, not {js(app, mw.web, stages)}")
    print("PASS: reload_addon swaps in the code on disk and redraws the window.")

    mw.addonManager.toggleEnabled("keshiki", False)
    until(app, lambda: not any(background_on(app, w) for w in webs), 10, "background stayed after turning off")
    mw.addonManager.toggleEnabled("keshiki", True)
    until(app, lambda: all(background_on(app, w) for w in webs), 10, "background didn't come back")
    print("PASS: turning Keshiki off in Tools > Add-ons clears the background at once, and on brings it back.")


if __name__ == "__main__":
    run(check, __doc__)
