# ShielyCapture

A small Mac menu bar screenshot tool with Snagit-style scrolling capture.
Everything goes to the clipboard as a PNG.

| Hotkey | Action |
| --- | --- |
| Ctrl+Shift+1 | Region |
| Ctrl+Shift+2 | Full screen |
| Ctrl+Shift+3 | Window |
| Ctrl+Shift+4 | Scroll capture |

## Scroll capture

1. Scroll your page to where you want to start.
2. Press Ctrl+Shift+4. Click a window (it highlights on hover) or drag an area.
3. Scroll normally. Frames are captured silently about ten times a second. A red frame marks the area.
4. Press Return to stitch and copy. Esc cancels. Ctrl+Shift+4 again also finishes.

Sounds: Tink when recording starts, Pop when copied, Basso on cancel, Funk if you
scrolled too fast to track (scroll back up a little and it recovers). The menu
bar shows a recording dot with a frame count, then a check mark after a copy.

## Setup

Requires Homebrew Python (`brew install python`). It deliberately does not use
`/usr/bin/python3`, which is the Xcode shim and fails until the Xcode license is accepted.

```bash
./setup.sh                 # venv + signed ShielyCapture.app wrapper
./start.sh                 # run it now
./install_login_agent.sh   # run at every login (uninstall_login_agent.sh removes it)
```

On the first capture macOS asks for Screen Recording. Allow **ShielyCapture**.
The app is a renamed, ad-hoc-signed copy of Python.app so the permission prompt
shows that name instead of "Python". If Homebrew upgrades Python, run `./setup.sh` again.

Log: `~/Library/Logs/shiely_capture.log`

## How it works

- **Hotkeys** use Carbon `RegisterEventHotKey`, which needs no Accessibility or
  Input Monitoring permission (an `NSEvent` global monitor silently does nothing without them).
- **Scroll capture** polls `screencapture -R` on the chosen rectangle. For each frame
  it finds the vertical shift against the previous frame by matching row signatures
  (coarse search, then full-resolution refinement). Rows that are identical between
  frames are treated as static UI (sticky headers) and ignored. Rows are committed
  only from above each frame's bottom margin, so window corners and Chrome's link
  bubble never land mid-page.
- **Stitching** is incremental and supports scrolling up and down.

## Tests

```bash
./venv/bin/python tests/test_stitch.py
```

Scrolls a synthetic tall page past the stitcher at several speeds, with a sticky
header and bottom-edge artifacts, and checks the result pixel for pixel.

## Known limits

- Very fast flicks (roughly 4000 px/s or more) lose tracking. Nothing is corrupted.
- A sticky footer repeats in the stitched image.
- Live screen capture cannot be exercised headlessly, only the stitching is unit tested.
