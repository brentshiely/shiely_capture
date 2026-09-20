# ShielyCapture

A small Mac menu bar screenshot tool with Snagit-style scrolling capture.
Everything goes to the clipboard as a PNG.

Built by pairing with an AI engineer (Claude Code) and tested by hand on real pages.
Status: works on macOS 26 on Apple Silicon. Other setups are untested.
This is source code, not a download: there is no installer yet (see "Who this is for").

## Who this is for

**If you are comfortable with code**, clone it and run the setup below.

**If you use an AI as your engineer**, point it at this repo and let it do the setup and review.
Paste this into your assistant:

> Clone https://github.com/brentshiely/shiely_capture and read `AGENTS.md` and `README.md`.
> Review the code for bugs and security problems and tell me what you find. Then set it up on
> my Mac using `setup.sh`, walk me through the Screen Recording permission, and confirm each
> of the four hotkeys works with me.

`AGENTS.md` holds the non-obvious details an engineer needs (permission quirks, what can and
cannot be tested, the stitching invariants).

| Hotkey | Action |
| --- | --- |
| Ctrl+Shift+1 | Region (reopens your last frame) |
| Ctrl+Shift+2 | Full screen |
| Ctrl+Shift+3 | Window |
| Ctrl+Shift+4 | Scroll capture |
| Ctrl+Shift+5 | Silent video of a window or area |

## Region capture

Press Ctrl+Shift+1 and a frame appears where you last captured, at the same size. Drag its
sides or corners to resize, drag inside to move it, or use the arrow keys to nudge it (hold
Shift for 10 points at a time). Drag outside the frame to draw a new one. Press Return to
capture, Esc to cancel. The frame is remembered between captures and restarts, so repeated
captures of the same area need no redrawing.

## Scroll capture

1. Scroll your page to where you want to start.
2. Press Ctrl+Shift+4. Click a window (it highlights on hover) or drag an area.
3. Scroll normally. Frames are captured silently about ten times a second. A red frame marks the area.
4. Press Return to stitch and copy. Esc cancels. Ctrl+Shift+4 again also finishes.

Sounds: Tink when recording starts, Pop when copied, Basso on cancel, Funk if you
scrolled too fast to track (scroll back up a little and it recovers). The menu
bar shows a recording dot with a frame count, then a check mark after a copy.

## Video capture

Press Ctrl+Shift+5, click a window or drag an area, and it records the screen with no audio.
Press Ctrl+Shift+5 again or Return to stop, or Esc to discard. The `.mov` is saved to
`~/Movies/ShielyCapture/` and the file is also placed on the clipboard, so you can paste it
into Slack, Mail or Messages. It records that rectangle of the screen, so a window that
covers the target would appear in the video.

## Setup

Requires macOS on Apple Silicon and Homebrew Python (`brew install python`). It deliberately
does not use `/usr/bin/python3`, which is the Xcode shim and fails until the Xcode license is accepted.

```bash
git clone https://github.com/brentshiely/shiely_capture.git
cd shiely_capture
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
- **Video** shells out to `screencapture -v -R` and stops it with SIGINT so the file is finalized.

## Tests

```bash
./venv/bin/python tests/test_stitch.py   # scrolling stitcher
./venv/bin/python tests/test_frame.py    # region frame geometry and persistence
```

Scrolls a synthetic tall page past the stitcher at several speeds, with a sticky
header and bottom-edge artifacts, and checks the result pixel for pixel.

## How it was built

It started as a script whose hotkeys did nothing and whose LaunchAgent never ran. Two root
causes: it launched through the Xcode-shim Python, and it listened for keys with `NSEvent`
monitors that fail silently without Input Monitoring. Fixes were Carbon hotkeys and a dedicated
venv. The scrolling capture was then rebuilt around a stitcher developed against synthetic
scrolling pages, with hand testing on real pages finding what the tests missed (an overlay
that gave no instructions, window corners and link bubbles at the seams, sticky headers
defeating the matcher). `AGENTS.md` records those lessons.

## Known limits

- Very fast flicks (roughly 4000 px/s or more) lose tracking. Nothing is corrupted.
- A sticky footer repeats in the stitched image.
- Live screen capture and video cannot be exercised headlessly, only the stitching is unit tested.
- Video has no audio yet. Window audio plus narration with a mute control is planned (ScreenCaptureKit via a Swift helper).

## License

MIT. See `LICENSE`.
