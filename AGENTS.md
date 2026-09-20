# Notes for AI coding assistants

Read this first if you are an AI engineer asked to review, run, debug or extend this repo.
`README.md` covers usage. This file covers what is not obvious from the code.

## What this is

ShielyCapture is a single-file macOS menu bar app (`shiely_capture.py`, Python + PyObjC + rumps).
Global hotkeys take screenshots to the clipboard. Ctrl+Shift+4 is a Snagit-style scrolling
capture: the user selects a window or area, scrolls normally, and Return stitches the frames.

## Layout

- `shiely_capture.py`: everything. Sections: clipboard, Carbon hotkeys, region selector overlay,
  stitching (`find_shift`, `Stitcher`), `ScrollSession` thread, `App` (rumps).
- `tests/test_stitch.py`: pixel-exact stitcher tests on a synthetic tall page. Run these after any
  change to matching or stitching: `./venv/bin/python tests/test_stitch.py`
- `setup.sh`: builds `venv/` and `ShielyCapture.app` (a renamed, ad-hoc-signed copy of Homebrew's
  Python.app, so macOS permission prompts say "ShielyCapture" instead of "Python").
- `start.sh`, `stop.sh`, `install_login_agent.sh`, `uninstall_login_agent.sh`: run and manage it.

## Gotchas that already cost us time

- **Never assume `/usr/bin/python3` or `/usr/bin/git` work.** On a Mac where the Xcode license has
  not been accepted they are shims that fail (sometimes silently inside heredocs). Use
  `./venv/bin/python`, Homebrew Python, and check `git --version` before relying on it.
- **Hotkeys use Carbon `RegisterEventHotKey`, deliberately.** An `NSEvent` global monitor needs
  Input Monitoring for the exact binary and fails silently without it. Do not switch back.
- **Screen Recording is granted to the `ShielyCapture.app` identity.** Start it through
  `start.sh` (LaunchServices) or the LaunchAgent, not by running the binary from a terminal, or
  macOS attributes the permission to the terminal instead. Re-signing changes the identity and
  can force the user to re-grant.
- **You cannot test live capture headlessly.** `screencapture` fails ("could not create image")
  in sandboxed shells without Screen Recording. Only the stitcher is unit-testable. Say so
  plainly if you cannot verify a capture-path change, and ask the user to try it.
- **Sudo, permissions and system settings are the user's.** Do not attempt to change privacy
  settings or accept licenses on their behalf.

## Stitching invariants (do not break these)

- Match by row signatures, coarse then fine. Rank candidates by `matched_rows * fraction**4`.
  Ranking by fraction alone or count alone both failed on periodic text.
- Ignore rows identical between two frames at the same position (sticky headers). Counting them
  as mismatches makes the true shift fall under the acceptance threshold.
- Commit new rows only from above each frame's bottom margin. Window corners and Chrome's link
  status bubble live at the bottom edge and otherwise land mid-page.
- A failed match leaves the previous frame in place, so scrolling back recovers. A wrong
  match corrupts the output, so prefer "no match" over a weak match (`MIN_MATCH_ROWS`, fraction >= 0.6).

## Known limits and reasonable next steps

- Very fast flicks (about 4000 px/s or more) lose tracking. A sticky footer repeats in the output.
- Not yet packaged for non-technical users. The path is py2app or PyInstaller, then Developer ID
  signing and notarization (needs a paid Apple Developer account), then a DMG.
- Hotkeys are hardcoded. A preferences pane or config file would be a natural addition.
- Apple Silicon and macOS 26 are the only tested platform.

## Style

Plain code, short comments only where the reason is not obvious. Keep the README free of hype.
