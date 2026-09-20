#!/usr/bin/env python3
"""
shiely_capture v7

Ctrl+Shift+1  region -> clipboard
Ctrl+Shift+2  full screen -> clipboard
Ctrl+Shift+3  window -> clipboard
Ctrl+Shift+4  scroll capture (Snagit style):
                drag a region, then scroll normally. Frames are captured
                silently in the background. Return = stitch and copy,
                Esc = cancel. (Ctrl+Shift+4 again also finishes.)

Hotkeys use Carbon RegisterEventHotKey, which needs no Accessibility or
Input Monitoring permission. Scroll capture needs Screen Recording permission
for the Python binary that runs this script.
"""

import ctypes
import io
import os
import subprocess
import sys
import tempfile
import threading
import time
import traceback

import numpy as np
import objc
import rumps
from AppKit import (
    NSApplication, NSBackingStoreBuffered, NSBezierPath, NSColor, NSCursor,
    NSEvent, NSFont, NSFontAttributeName, NSForegroundColorAttributeName,
    NSPasteboard, NSPasteboardTypePNG, NSScreen, NSSound, NSString, NSTrackingActiveAlways,
    NSTrackingArea, NSTrackingInVisibleRect, NSTrackingMouseMoved, NSView,
    NSWindow, NSWorkspace,
)
from PIL import Image
from Quartz import (
    CGShieldingWindowLevel, CGWindowListCopyWindowInfo, kCGNullWindowID,
    kCGWindowListExcludeDesktopElements, kCGWindowListOptionOnScreenOnly,
)

KEY_1, KEY_2, KEY_3, KEY_4 = 18, 19, 20, 21
KEY_RETURN, KEY_ENTER, KEY_ESC = 36, 76, 53
MOD_SHIFT, MOD_CONTROL = 512, 4096

POLL_SECONDS = 0.10
MAX_CANVAS_ROWS = 60000
MIN_MATCH_ROWS = 30


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def play(name):
    try:
        s = NSSound.soundNamed_(name)
        if s:
            s.stop()
            s.play()
    except Exception:
        pass


# ----------------------------------------------------------------- clipboard

def to_clipboard(im):
    b = io.BytesIO()
    im.save(b, format="PNG")
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.declareTypes_owner_([NSPasteboardTypePNG], None)
    pb.setData_forType_(b.getvalue(), NSPasteboardTypePNG)
    log(f"copied {im.width}x{im.height}")


# ------------------------------------------------------------ carbon hotkeys

_carbon = ctypes.CDLL("/System/Library/Frameworks/Carbon.framework/Carbon")


class _EventTypeSpec(ctypes.Structure):
    _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]


class _HotKeyID(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]


_HANDLER_T = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
_carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
_carbon.InstallEventHandler.argtypes = [
    ctypes.c_void_p, _HANDLER_T, ctypes.c_ulong,
    ctypes.POINTER(_EventTypeSpec), ctypes.c_void_p, ctypes.c_void_p]
_carbon.RegisterEventHotKey.argtypes = [
    ctypes.c_uint32, ctypes.c_uint32, _HotKeyID, ctypes.c_void_p,
    ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
_carbon.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
_carbon.GetEventParameter.argtypes = [
    ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
    ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p]

_SIG = 0x53484C59  # 'SHLY'


class Hotkeys:
    def __init__(self, on_press):
        self.on_press = on_press
        self.refs = {}
        self._cb = _HANDLER_T(self._handler)  # keep a reference alive
        spec = _EventTypeSpec(0x6B657962, 5)  # 'keyb', kEventHotKeyPressed
        st = _carbon.InstallEventHandler(
            _carbon.GetApplicationEventTarget(), self._cb, 1,
            ctypes.byref(spec), None, None)
        if st:
            log("InstallEventHandler failed", st)

    def _handler(self, _next, event, _user):
        hk = _HotKeyID()
        _carbon.GetEventParameter(event, 0x2D2D2D2D, 0x686B6964, None,
                                  ctypes.sizeof(hk), None, ctypes.byref(hk))
        try:
            self.on_press(hk.id)
        except Exception:
            traceback.print_exc()
        return 0

    def register(self, hid, keycode, mods):
        if hid in self.refs:
            return
        ref = ctypes.c_void_p()
        st = _carbon.RegisterEventHotKey(
            keycode, mods, _HotKeyID(_SIG, hid),
            _carbon.GetApplicationEventTarget(), 0, ctypes.byref(ref))
        if st:
            log(f"RegisterEventHotKey id={hid} key={keycode} failed status={st}")
        else:
            self.refs[hid] = ref

    def unregister(self, hid):
        ref = self.refs.pop(hid, None)
        if ref:
            _carbon.UnregisterEventHotKey(ref)


# ---------------------------------------------------------- one-shot capture

def _screencapture(*args, timeout=120):
    try:
        subprocess.run(["screencapture", "-c", *args], timeout=timeout,
                       capture_output=True)
    except Exception:
        log("screencapture failed")
        traceback.print_exc()


# ----------------------------------------------------------- region selector

def _window_under(gx, gy):
    """Frontmost normal window containing the global top-left point.
    Returns (x, y, w, h) in top-left global coordinates, or None."""
    me = os.getpid()
    infos = CGWindowListCopyWindowInfo(
        kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
        kCGNullWindowID) or []
    for w in infos:
        if w.get("kCGWindowLayer") != 0 or w.get("kCGWindowOwnerPID") == me:
            continue
        b = w.get("kCGWindowBounds")
        x, y, ww, hh = b["X"], b["Y"], b["Width"], b["Height"]
        if ww < 120 or hh < 120:
            continue
        if x <= gx <= x + ww and y <= gy <= y + hh:
            return (int(x), int(y), int(ww), int(hh))
    return None


class _SelView(NSView):
    HINT = "Click a window, or drag an area, then scroll.   Esc cancels."

    def initWithFrame_(self, frame):
        self = objc.super(_SelView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.p0 = None
        self.p1 = None
        self.hover = None      # window rect, top-left global coords
        self.finish = None
        return self

    def acceptsFirstResponder(self):
        return True

    def acceptsFirstMouse_(self, ev):
        return True

    def updateTrackingAreas(self):
        objc.super(_SelView, self).updateTrackingAreas()
        for t in list(self.trackingAreas()):
            self.removeTrackingArea_(t)
        opts = NSTrackingMouseMoved | NSTrackingActiveAlways | NSTrackingInVisibleRect
        self.addTrackingArea_(NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            self.bounds(), opts, self, None))

    def resetCursorRects(self):
        self.addCursorRect_cursor_(self.bounds(), NSCursor.crosshairCursor())

    def _rect(self):
        (x0, y0), (x1, y1) = self.p0, self.p1
        return (min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))

    def _to_view(self, r):
        """top-left global rect -> this view's coordinates"""
        f = self.window().frame().origin
        x, y, w, h = r
        return (x - f.x, (_primary_height() - (y + h)) - f.y, w, h)

    def mouseMoved_(self, ev):
        if self.p0:
            return
        m = NSEvent.mouseLocation()
        self.hover = _window_under(m.x, _primary_height() - m.y)
        self.setNeedsDisplay_(True)

    def mouseDown_(self, ev):
        p = ev.locationInWindow()
        self.p0 = self.p1 = (p.x, p.y)
        self.setNeedsDisplay_(True)

    def mouseDragged_(self, ev):
        p = ev.locationInWindow()
        self.p1 = (p.x, p.y)
        self.setNeedsDisplay_(True)

    def mouseUp_(self, ev):
        p = ev.locationInWindow()
        self.p1 = (p.x, p.y)
        x, y, w, h = self._rect()
        self.p0 = None
        self.setNeedsDisplay_(True)
        if w < 8 and h < 8:                      # a click: take the hovered window
            if self.hover and self.finish:
                hx, hy, hw, hh = self.hover
                self.finish((hx, _primary_height() - (hy + hh), hw, hh))
            return
        if w < 40 or h < 40:                     # accidental tiny drag
            return
        origin = self.window().convertPointToScreen_((x, y))
        if self.finish:
            self.finish((origin.x, origin.y, w, h))

    def keyDown_(self, ev):
        if ev.keyCode() == KEY_ESC and self.finish:
            self.finish(None)

    def drawRect_(self, rect):
        NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.25).set()
        NSBezierPath.fillRect_(self.bounds())
        if self.hover and not self.p0:
            hx, hy, hw, hh = self._to_view(self.hover)
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.2, 0.5, 1, 0.18).set()
            NSBezierPath.fillRect_(((hx, hy), (hw, hh)))
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.2, 0.5, 1, 1).set()
            path = NSBezierPath.bezierPathWithRect_(((hx, hy), (hw, hh)))
            path.setLineWidth_(3)
            path.stroke()
        if self.p0:
            x, y, w, h = self._rect()
            NSColor.colorWithCalibratedRed_green_blue_alpha_(1, 0.2, 0.2, 0.12).set()
            NSBezierPath.fillRect_(((x, y), (w, h)))
            NSColor.colorWithCalibratedRed_green_blue_alpha_(1, 0.2, 0.2, 1).set()
            path = NSBezierPath.bezierPathWithRect_(((x, y), (w, h)))
            path.setLineWidth_(2)
            path.stroke()
        self._draw_banner()

    def _draw_banner(self):
        attrs = {NSFontAttributeName: NSFont.boldSystemFontOfSize_(18),
                 NSForegroundColorAttributeName: NSColor.whiteColor()}
        s = NSString.stringWithString_(self.HINT)
        sz = s.sizeWithAttributes_(attrs)
        b = self.bounds()
        w, h = sz.width + 48, sz.height + 24
        x, y = (b.size.width - w) / 2, b.size.height - h - 90
        NSColor.colorWithCalibratedWhite_alpha_(0.05, 0.85).set()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(((x, y), (w, h)), 12, 12).fill()
        s.drawAtPoint_withAttributes_((x + 24, y + 12), attrs)


class _BorderView(NSView):
    def drawRect_(self, rect):
        NSColor.colorWithCalibratedRed_green_blue_alpha_(1, 0.2, 0.2, 1).set()
        b = self.bounds()
        path = NSBezierPath.bezierPathWithRect_(
            ((1.5, 1.5), (b.size.width - 3, b.size.height - 3)))
        path.setLineWidth_(3)
        path.stroke()


class _KeyWindow(NSWindow):
    def canBecomeKeyWindow(self):
        return True


def _make_window(frame, view_cls, level, click_through):
    w = _KeyWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        frame, 0, NSBackingStoreBuffered, False)
    w.setOpaque_(False)
    w.setBackgroundColor_(NSColor.clearColor())
    w.setLevel_(level)
    w.setHasShadow_(False)
    w.setReleasedWhenClosed_(False)
    w.setIgnoresMouseEvents_(click_through)
    v = view_cls.alloc().initWithFrame_(((0, 0), frame[1]))
    w.setContentView_(v)
    return w, v


def _primary_height():
    return NSScreen.screens()[0].frame().size.height


class Selector:
    """Full-screen drag-to-select overlay. Calls done(rect_top_left | None)."""

    def __init__(self, done):
        self.done = done
        self.wins = []
        self.prev_app = NSWorkspace.sharedWorkspace().frontmostApplication()

    def show(self):
        level = CGShieldingWindowLevel()
        for scr in NSScreen.screens():
            w, v = _make_window(scr.frame(), _SelView, level, False)
            v.finish = self._finish
            w.setAcceptsMouseMovedEvents_(True)
            self.wins.append((w, v))
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        for w, v in self.wins:
            w.makeKeyAndOrderFront_(None)
            w.makeFirstResponder_(v)

    def _finish(self, rect):
        for w, _ in self.wins:
            w.orderOut_(None)
        self.wins = []
        try:
            if self.prev_app:
                self.prev_app.activateWithOptions_(2)
        except Exception:
            pass
        if rect:
            x, y, w, h = rect
            rect = (int(round(x)), int(round(_primary_height() - (y + h))),
                    int(round(w)), int(round(h)))
        self.done(rect)


# --------------------------------------------------------------- stitching

def _sigs(g):
    """Fine (H x 64) and coarse (H/4 x 32) row signatures of a gray image."""
    H, W = g.shape
    bw = W // 64
    f = g[:, :bw * 64].reshape(H, 64, bw).mean(axis=2).astype(np.float32)
    Hc = H // 4
    c = f[:Hc * 4].reshape(Hc, 4, 64).mean(axis=1).reshape(Hc, 32, 2).mean(axis=2)
    return f, c


def _match(A, B, tol, tex_thr, skip=None):
    """Count textured rows of A that match B. Returns (matched, fraction, textured).
    skip marks rows to ignore (static UI such as sticky headers)."""
    tex = A.std(axis=1) > tex_thr
    if skip is not None:
        tex &= ~skip
    n_tex = int(tex.sum())
    if n_tex == 0:
        return 0, 0.0, 0
    d = np.abs(A - B).mean(axis=1)
    m = int(((d < tol) & tex).sum())
    return m, m / n_tex, n_tex


def _static_rows(a, b):
    """Rows identical at the same position in both frames: sticky bars, not content."""
    return np.abs(a - b).mean(axis=1) < 1.0


def _down_candidates(pc, cc, min_overlap, static):
    """Coarse search: pc[s:] ~ cc[:n-s]. Returns top (score, s) pairs."""
    n = len(pc)
    out = []
    for s in range(1, n - min_overlap + 1):
        m, fr, nt = _match(pc[s:], cc[:n - s], 14, 4, static[s:] | static[:n - s])
        if nt >= 6 and fr >= 0.5:
            out.append((m * fr ** 4, m, s))
    out.sort(reverse=True)
    return [(m, s) for _, m, s in out[:5]]


def _refine_down(pf, cf, s_coarse, min_overlap_px, static):
    H = len(pf)
    best = (0, 0.0, 0)
    for s in range(max(1, 4 * s_coarse - 6), min(H - min_overlap_px, 4 * s_coarse + 6) + 1):
        m, fr, nt = _match(pf[s:], cf[:H - s], 8, 6, static[s:] | static[:H - s])
        if nt >= 12 and m * fr ** 4 > best[0] * best[1] ** 4:
            best = (m, fr, s)
    return best


def find_shift(prev_sig, cur_sig):
    """Vertical scroll between two frames. >0 means content moved up (scrolled down).
    Returns (shift_px, quality) or None if no confident match."""
    pf, pc = prev_sig
    cf, cc = cur_sig
    H = len(pf)
    min_ov = max(40, int(H * 0.12))
    static_f = _static_rows(pf, cf)
    static_c = _static_rows(pc, cc)
    best = None
    for sign, (af, ac, bf, bc) in ((1, (pf, pc, cf, cc)), (-1, (cf, cc, pf, pc))):
        for _, sc in _down_candidates(ac, bc, min_ov // 4, static_c):
            m, fr, s = _refine_down(af, bf, sc, min_ov, static_f)
            if s and fr >= 0.6 and m >= MIN_MATCH_ROWS and (best is None or m * fr ** 4 > best[0] * best[1] ** 4):
                best = (m, fr, sign * s)
    if best is None:
        return None
    return best[2], best[1]


class Stitcher:
    """Incrementally builds a tall image from overlapping frames (RGB arrays).

    Rows are committed only from above each frame's bottom margin, so window
    corners and Chrome's link-status bubble at the bottom edge never land
    mid-page. The last frame supplies whatever is left at the end."""

    def __init__(self):
        self.strips = []
        self.total = 0        # canvas rows committed so far
        self.pos = 0          # canvas row of the top of the last accepted frame
        self.prev = None      # (rgb, sig)
        self.frames_seen = 0
        self.frames_used = 0

    @staticmethod
    def _gray(rgb):
        return np.asarray(Image.fromarray(rgb).convert("L"))

    @staticmethod
    def _margin(H):
        return max(60, int(H * 0.06))

    def add(self, rgb):
        self.frames_seen += 1
        H = rgb.shape[0]
        if self.prev is None:
            keep = H - self._margin(H)
            self.strips.append(rgb[:keep])
            self.total = keep
            self.prev = (rgb, _sigs(self._gray(rgb)))
            self.frames_used = 1
            return "first"
        prgb, psig = self.prev
        if rgb.shape != prgb.shape:
            return "size-changed"
        if np.array_equal(rgb[::3, ::3], prgb[::3, ::3]):
            return "same"
        sig = _sigs(self._gray(rgb))
        r = find_shift(psig, sig)
        if r is None:
            return "no-match"
        s, _ = r
        newpos = self.pos + s
        if newpos < 0:
            return "above-start"
        limit = newpos + H - self._margin(H)
        if limit > MAX_CANVAS_ROWS:
            return "too-tall"
        if self.total < newpos:  # jumped past the margin: previous frame covers the gap
            self.strips.append(prgb[self.total - self.pos:newpos - self.pos])
            self.total = newpos
        if limit > self.total:
            self.strips.append(rgb[self.total - newpos:limit - newpos])
            self.total = limit
        self.pos = newpos
        self.prev = (rgb, sig)
        self.frames_used += 1
        return f"shift {s}"

    def result(self):
        if not self.strips:
            return None
        last = self.prev[0]
        tail = last[self.total - self.pos:]
        parts = self.strips + ([tail] if tail.shape[0] else [])
        if len(parts) == 1:
            return Image.fromarray(parts[0])
        return Image.fromarray(np.concatenate(parts, axis=0))


# ---------------------------------------------------------- scroll session

class ScrollSession(threading.Thread):
    def __init__(self, rect, on_done):
        super().__init__(daemon=True)
        self.rect = rect
        self.on_done = on_done
        self.stop_flag = threading.Event()
        self.cancelled = False
        self.stitcher = Stitcher()
        self.tmpdir = tempfile.mkdtemp(prefix="shiely_")

    @property
    def frames(self):
        return self.stitcher.frames_used

    def _grab(self):
        x, y, w, h = self.rect
        path = os.path.join(self.tmpdir, "f.png")
        subprocess.run(["screencapture", "-x", "-t", "png", "-R", f"{x},{y},{w},{h}", path],
                       timeout=6, capture_output=True)
        if not os.path.exists(path):
            return None
        im = Image.open(path).convert("RGB")
        arr = np.asarray(im).copy()
        os.unlink(path)
        return arr

    def _step(self):
        arr = self._grab()
        if arr is None:
            return "grab-failed"
        return self.stitcher.add(arr)

    def run(self):
        misses = 0
        lost = 0
        try:
            time.sleep(0.15)
            while not self.stop_flag.is_set():
                t0 = time.time()
                r = self._step()
                if r == "grab-failed":
                    misses += 1
                    if misses >= 5:
                        log("screen grabs failing: Screen Recording permission?")
                        self.cancelled = True
                        break
                else:
                    misses = 0
                    if r != "same":
                        log("frame:", r)
                    if r in ("no-match", "size-changed"):
                        lost += 1
                        if lost == 6:  # scrolled too fast to track: scroll back up a bit
                            play("Funk")
                    elif r != "same":
                        lost = 0
                time.sleep(max(0.0, POLL_SECONDS - (time.time() - t0)))
            if not self.cancelled:
                time.sleep(0.15)
                self._step()  # settle frame
        except Exception:
            traceback.print_exc()
            self.cancelled = True
        finally:
            img = None if self.cancelled else self.stitcher.result()
            try:
                for f in os.listdir(self.tmpdir):
                    os.unlink(os.path.join(self.tmpdir, f))
                os.rmdir(self.tmpdir)
            except Exception:
                pass
            self.on_done(img)


# ---------------------------------------------------------------- the app

HK_REGION, HK_FULL, HK_WINDOW, HK_SCROLL, HK_RET, HK_ESC, HK_ENTER = 1, 2, 3, 4, 10, 11, 12


class App(rumps.App):
    def __init__(self):
        super().__init__("⌗", quit_button=None)
        self.menu = [
            rumps.MenuItem("Region  ⌃⇧1", callback=lambda _: self.region()),
            rumps.MenuItem("Full screen  ⌃⇧2", callback=lambda _: self.fullscreen()),
            rumps.MenuItem("Window  ⌃⇧3", callback=lambda _: self.window()),
            rumps.MenuItem("Scroll  ⌃⇧4", callback=lambda _: self.scroll()),
            None,
            rumps.MenuItem("Quit", callback=rumps.quit_application),
        ]
        self.busy = False
        self.session = None
        self.selector = None
        self.border = None
        self.flash_until = 0
        self.hotkeys = Hotkeys(self.on_hotkey)
        for hid, key in ((HK_REGION, KEY_1), (HK_FULL, KEY_2), (HK_WINDOW, KEY_3), (HK_SCROLL, KEY_4)):
            self.hotkeys.register(hid, key, MOD_CONTROL | MOD_SHIFT)
        self.ticker = rumps.Timer(self._tick, 0.4)
        self.ticker.start()
        log("ready; hotkeys registered:", sorted(self.hotkeys.refs))

    # -- status item
    def _tick(self, _):
        if self.session and not self.session.is_alive():
            self._cleanup_session()
        if self.session:
            self.title = f"⏺ {self.session.frames}"
        elif time.time() < self.flash_until:
            self.title = "✓"
        elif self.selector:
            self.title = "⌗…"
        else:
            self.title = "⌗"

    # -- hotkey dispatch (runs on main thread)
    def on_hotkey(self, hid):
        log("hotkey", hid)
        if hid == HK_REGION:
            self.region()
        elif hid == HK_FULL:
            self.fullscreen()
        elif hid == HK_WINDOW:
            self.window()
        elif hid == HK_SCROLL:
            self.scroll()
        elif hid in (HK_RET, HK_ENTER):
            self.finish_scroll(cancel=False)
        elif hid == HK_ESC:
            self.finish_scroll(cancel=True)

    # -- one-shot captures
    def _oneshot(self, *args):
        if self.busy:
            return
        self.busy = True

        def work():
            try:
                _screencapture(*args)
            finally:
                self.busy = False
        threading.Thread(target=work, daemon=True).start()

    def region(self):
        self._oneshot("-i")

    def fullscreen(self):
        self._oneshot()

    def window(self):
        self._oneshot("-i", "-w")

    # -- scroll capture
    def scroll(self):
        if self.session:
            self.finish_scroll(cancel=False)
            return
        if self.busy or self.selector:
            return
        self.selector = Selector(self._region_chosen)
        self.selector.show()

    def _region_chosen(self, rect):
        self.selector = None
        if not rect:
            play("Basso")
            return
        x, y, w, h = rect
        # red frame just outside the captured area, so it never appears in frames
        pad = 4
        ph = _primary_height()
        frame = ((x - pad, ph - (y + h) - pad), (w + 2 * pad, h + 2 * pad))
        win, _ = _make_window(frame, _BorderView, CGShieldingWindowLevel(), True)
        win.orderFrontRegardless()
        self.border = win
        self.busy = True
        self.session = ScrollSession(rect, self._session_done)
        self.hotkeys.register(HK_RET, KEY_RETURN, 0)
        self.hotkeys.register(HK_ENTER, KEY_ENTER, 0)
        self.hotkeys.register(HK_ESC, KEY_ESC, 0)
        play("Tink")
        log("scroll capture started", rect)
        self.session.start()

    def finish_scroll(self, cancel):
        s = self.session
        if not s or s.stop_flag.is_set():
            return
        s.cancelled = s.cancelled or cancel
        s.stop_flag.set()
        self._end_ui()

    def _end_ui(self):
        for hid in (HK_RET, HK_ENTER, HK_ESC):
            self.hotkeys.unregister(hid)
        if self.border:
            self.border.orderOut_(None)
            self.border = None

    def _cleanup_session(self):
        self._end_ui()
        self.session = None
        self.busy = False

    def _session_done(self, img):
        # runs on the session thread
        if img is None:
            log("scroll capture cancelled")
            play("Basso")
            return
        try:
            to_clipboard(img)
            self.flash_until = time.time() + 2.5
            play("Pop")
        except Exception:
            traceback.print_exc()
            play("Basso")


if __name__ == "__main__":
    NSApplication.sharedApplication().setActivationPolicy_(1)  # accessory: no Dock icon
    App().run()
