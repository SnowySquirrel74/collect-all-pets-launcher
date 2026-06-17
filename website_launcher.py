import base64
import ctypes
import datetime as dt
import gzip
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import zlib
from ctypes import wintypes
from pathlib import Path
from tkinter import messagebox, ttk
import tkinter as tk

from PIL import ImageChops, ImageGrab, ImageStat


APP_NAME = "Collect All Pets"
APP_DIR = Path(__file__).resolve().parent


def settings_file_path():
    if getattr(sys, "frozen", False):
        if os.name == "nt":
            base_dir = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        else:
            base_dir = Path.home() / ".config"
        data_dir = base_dir / APP_NAME
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / "website_launcher_settings.json"
    return APP_DIR / "website_launcher_settings.json"


SETTINGS_FILE = settings_file_path()
ULONG_PTR = wintypes.WPARAM
PASSWORD_TARGET = "CollectAllPetsServerLauncher"
ROBLOX_PROCESS = "RobloxPlayerBeta.exe"
ROBLOX_MULTI_MUTEX = "ROBLOX_singletonMutex"
WAIT_OBJECT_0 = 0x00000000
WAIT_ABANDONED = 0x00000080
WAIT_TIMEOUT = 0x00000102
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MAPVK_VK_TO_VSC = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
DEFAULT_KEEP_ALIVE_MINUTES = 5
DEFAULT_POPUP_SENSITIVITY = 50
DEFAULT_ACTIVITY_SENSITIVITY = 50
DEFAULT_DETECTOR_SAMPLE_COUNT = 3
DEFAULT_DETECTOR_SAMPLE_DELAY = 0.65
DEFAULT_DISCONNECT_MODAL_DARK_RATIO = 0.58
DEFAULT_DISCONNECT_MODAL_MEAN_LIMIT = 105
DEFAULT_MIN_ACTIVE_MOTION_SCORE = 0.35
MIN_TAB_RESPONSE_SCORE = 3.0
COLOR_BG = "#0f172a"
COLOR_SURFACE = "#f8fafc"
COLOR_CARD = "#ffffff"
COLOR_TEXT = "#111827"
COLOR_MUTED = "#64748b"
COLOR_BORDER = "#d8e0ea"
COLOR_PRIMARY = "#2563eb"
COLOR_PRIMARY_DARK = "#1d4ed8"
COLOR_SUCCESS = "#047857"
COLOR_WARNING = "#b45309"
COLOR_DANGER = "#dc2626"
COLOR_DANGER_DARK = "#b91c1c"


def enable_dpi_awareness():
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


enable_dpi_awareness()


class DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


class Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class Rect(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class KeyboardInput(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class InputUnion(ctypes.Union):
    _fields_ = [
        ("ki", KeyboardInput),
        ("mi", MouseInput),
        ("hi", HardwareInput),
    ]


class Input(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", InputUnion),
    ]


def hidden_process_flags():
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def protect_text(text):
    if os.name != "nt" or not text:
        return ""

    data = text.encode("utf-8")
    data_buffer = ctypes.create_string_buffer(data)
    in_blob = DataBlob(len(data), ctypes.cast(data_buffer, ctypes.POINTER(ctypes.c_char)))
    out_blob = DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        PASSWORD_TARGET,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    ):
        return ""

    try:
        encrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return base64.b64encode(encrypted).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def unprotect_text(value):
    if os.name != "nt" or not value:
        return ""

    try:
        encrypted = base64.b64decode(value)
    except Exception:
        return ""

    data_buffer = ctypes.create_string_buffer(encrypted)
    in_blob = DataBlob(len(encrypted), ctypes.cast(data_buffer, ctypes.POINTER(ctypes.c_char)))
    out_blob = DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    ):
        return ""

    try:
        data = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return data.decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def normalize_url(value):
    url = (value or "").strip()
    if not url:
        return ""
    if "://" not in url:
        url = f"https://{url}"
    return url


def automated_browser_candidates():
    local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
    program_files = [Path(os.environ.get("PROGRAMFILES", "")), Path(os.environ.get("PROGRAMFILES(X86)", ""))]

    candidates = []
    for root in program_files:
        if root:
            candidates.append(root / "Google" / "Chrome" / "Application" / "chrome.exe")
            candidates.append(root / "Microsoft" / "Edge" / "Application" / "msedge.exe")
    if local_app_data:
        candidates.append(local_app_data / "Google" / "Chrome" / "Application" / "chrome.exe")
        candidates.append(local_app_data / "Microsoft" / "Edge" / "Application" / "msedge.exe")
    return [path for path in candidates if path.exists()]


def free_local_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def roblox_login_url(target_url):
    return "https://www.roblox.com/login?returnUrl=" + urllib.parse.quote(target_url, safe="")


def parse_roblox_server_url(target_url):
    parsed = urllib.parse.urlparse(target_url)
    parts = [part for part in parsed.path.split("/") if part]
    place_id = ""
    if len(parts) >= 2 and parts[0].lower() == "games":
        place_id = parts[1]
    query = urllib.parse.parse_qs(parsed.query)
    private_code = (query.get("privateServerLinkCode") or query.get("code") or [""])[0]
    return place_id, private_code


def find_roblox_player():
    roots = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Roblox" / "Versions",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Roblox" / "Versions",
        Path(os.environ.get("PROGRAMFILES", "")) / "Roblox" / "Versions",
    ]
    candidates = []
    for root in roots:
        if root.exists():
            candidates.extend(root.glob("*/RobloxPlayerBeta.exe"))
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def is_roblox_running():
    return roblox_process_count() > 0


def roblox_process_count():
    if os.name != "nt":
        return 0
    result = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {ROBLOX_PROCESS}"],
        capture_output=True,
        text=True,
        creationflags=hidden_process_flags(),
    )
    return sum(1 for line in result.stdout.splitlines() if ROBLOX_PROCESS.lower() in line.lower())


def stop_roblox(wait=True, timeout=12):
    if os.name != "nt":
        return
    subprocess.run(
        ["taskkill", "/IM", ROBLOX_PROCESS, "/F"],
        capture_output=True,
        text=True,
        creationflags=hidden_process_flags(),
    )
    if not wait:
        return
    deadline = time.time() + timeout
    while time.time() < deadline:
        if roblox_process_count() == 0:
            return
        time.sleep(0.25)


def virtual_screen_geometry():
    if os.name != "nt":
        return 0, 0, 1200, 800
    user32 = ctypes.windll.user32
    left = user32.GetSystemMetrics(76)
    top = user32.GetSystemMetrics(77)
    width = user32.GetSystemMetrics(78)
    height = user32.GetSystemMetrics(79)
    return left, top, width, height


def fit_placement_to_virtual_screen(placement):
    if not placement:
        return None
    screen_left, screen_top, screen_width, screen_height = virtual_screen_geometry()
    screen_right = screen_left + screen_width
    screen_bottom = screen_top + screen_height

    width = max(120, min(int(placement["width"]), screen_width))
    height = max(120, min(int(placement["height"]), screen_height))
    x = max(screen_left, min(int(placement["x"]), screen_right - width))
    y = max(screen_top, min(int(placement["y"]), screen_bottom - height))
    return {"x": x, "y": y, "width": width, "height": height}


def clip_placement_to_virtual_screen(placement):
    if not placement:
        return None
    screen_left, screen_top, screen_width, screen_height = virtual_screen_geometry()
    screen_right = screen_left + screen_width
    screen_bottom = screen_top + screen_height

    left = max(screen_left, int(placement["x"]))
    top = max(screen_top, int(placement["y"]))
    right = min(screen_right, int(placement["x"]) + int(placement["width"]))
    bottom = min(screen_bottom, int(placement["y"]) + int(placement["height"]))
    if right - left < 40 or bottom - top < 40:
        return fit_placement_to_virtual_screen(placement)
    return {"x": left, "y": top, "width": right - left, "height": bottom - top}


def get_window_text(hwnd):
    user32 = ctypes.windll.user32
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def get_window_rect(hwnd):
    rect = Rect()
    if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return {
        "x": int(rect.left),
        "y": int(rect.top),
        "width": int(rect.right - rect.left),
        "height": int(rect.bottom - rect.top),
    }


def get_window_pid(hwnd):
    pid = wintypes.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def enum_roblox_windows():
    if os.name != "nt":
        return []
    user32 = ctypes.windll.user32
    windows = []

    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd) and get_window_text(hwnd) == "Roblox":
            placement = get_window_rect(hwnd)
            if placement and placement["width"] > 100 and placement["height"] > 100:
                windows.append({"hwnd": int(hwnd), "pid": get_window_pid(hwnd), "placement": placement})
        return True

    user32.EnumWindows(callback_type(callback), 0)
    return windows


def roblox_window_from_point(x, y):
    if os.name != "nt":
        return None
    user32 = ctypes.windll.user32
    user32.WindowFromPoint.argtypes = [Point]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    hwnd = user32.WindowFromPoint(Point(int(x), int(y)))
    if not hwnd:
        return None
    root = user32.GetAncestor(hwnd, 2) or hwnd
    if get_window_text(root) != "Roblox":
        return None
    placement = get_window_rect(root)
    if not placement:
        return None
    return {"hwnd": int(root), "pid": get_window_pid(root), "placement": placement}


def move_window_to_placement(hwnd, placement):
    if os.name != "nt" or not hwnd or not placement:
        return False
    placement = fit_placement_to_virtual_screen(placement)
    if not placement:
        return False
    return bool(
        ctypes.windll.user32.MoveWindow(
            wintypes.HWND(hwnd),
            int(placement["x"]),
            int(placement["y"]),
            int(placement["width"]),
            int(placement["height"]),
            True,
        )
    )


def is_window(hwnd):
    return bool(os.name == "nt" and hwnd and ctypes.windll.user32.IsWindow(wintypes.HWND(hwnd)))


def placement_distance(left, right):
    if not left or not right:
        return 999999
    return (
        abs(int(left["x"]) - int(right["x"]))
        + abs(int(left["y"]) - int(right["y"]))
        + abs(int(left["width"]) - int(right["width"]))
        + abs(int(left["height"]) - int(right["height"]))
    )


def find_window_by_placement(placement):
    if not placement:
        return None
    placement = fit_placement_to_virtual_screen(placement)
    candidates = enum_roblox_windows()
    if not candidates:
        return None
    best = min(candidates, key=lambda window: placement_distance(window["placement"], placement))
    return best if placement_distance(best["placement"], placement) < 220 else None


def wait_for_new_roblox_window(existing_hwnds, timeout=45):
    deadline = time.time() + timeout
    existing = {int(hwnd) for hwnd in existing_hwnds}
    while time.time() < deadline:
        for window in enum_roblox_windows():
            if int(window["hwnd"]) not in existing:
                return window
        time.sleep(0.5)
    return None


def focus_window(hwnd):
    if os.name != "nt" or not hwnd:
        return False
    user32 = ctypes.windll.user32
    user32.ShowWindow(wintypes.HWND(hwnd), 9)
    user32.BringWindowToTop(wintypes.HWND(hwnd))
    return bool(user32.SetForegroundWindow(wintypes.HWND(hwnd)))


def click_inside_window(hwnd):
    if os.name != "nt" or not hwnd:
        return False
    placement = get_window_rect(hwnd)
    if not placement:
        return False

    user32 = ctypes.windll.user32
    x = int(placement["x"] + placement["width"] * 0.50)
    y = int(placement["y"] + placement["height"] * 0.52)
    user32.SetCursorPos(x, y)
    time.sleep(0.08)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.06)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    return True


def press_key(vk_code):
    user32 = ctypes.windll.user32
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    scan_code = user32.MapVirtualKeyW(vk_code, MAPVK_VK_TO_VSC)
    inputs = (Input * 2)()
    inputs[0].type = INPUT_KEYBOARD
    inputs[0].union.ki = KeyboardInput(0, scan_code, KEYEVENTF_SCANCODE, 0, 0)
    inputs[1].type = INPUT_KEYBOARD
    inputs[1].union.ki = KeyboardInput(0, scan_code, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, 0)
    sent = user32.SendInput(2, ctypes.cast(inputs, ctypes.POINTER(Input)), ctypes.sizeof(Input))
    if sent != 2:
        user32.keybd_event(vk_code, scan_code, 0, 0)
        time.sleep(0.05)
        user32.keybd_event(vk_code, scan_code, KEYEVENTF_KEYUP, 0)


def send_keep_alive_keys(hwnd, tab_presses=2, c_presses=2):
    if os.name != "nt" or not hwnd:
        return False
    original_position = Point()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(original_position))
    try:
        focus_window(hwnd)
        time.sleep(0.25)
        click_inside_window(hwnd)
        time.sleep(0.20)
        for _index in range(max(1, int(tab_presses))):
            press_key(0x09)
            time.sleep(0.16)
        for _index in range(max(1, int(c_presses))):
            press_key(0x43)
            time.sleep(0.16)
    finally:
        ctypes.windll.user32.SetCursorPos(original_position.x, original_position.y)
    return True


def resolve_capture_placement(placement=None, hwnd=None):
    if hwnd and is_window(hwnd):
        current = get_window_rect(hwnd)
        if current:
            placement = current
    return clip_placement_to_virtual_screen(placement)


def capture_window_image(placement=None, hwnd=None):
    placement = resolve_capture_placement(placement, hwnd)
    if not placement:
        return None
    left = int(placement["x"])
    top = int(placement["y"])
    right = left + int(placement["width"])
    bottom = top + int(placement["height"])
    return ImageGrab.grab((left, top, right, bottom)).convert("RGB")


def relative_box(image, left, top, right, bottom):
    width, height = image.size
    return (
        int(width * left),
        int(height * top),
        int(width * right),
        int(height * bottom),
    )


def disconnect_modal_score(image, dark_ratio_limit=DEFAULT_DISCONNECT_MODAL_DARK_RATIO, mean_limit=DEFAULT_DISCONNECT_MODAL_MEAN_LIMIT):
    if not image:
        return {"modal": False, "dark_ratio": 0, "mean": 0}
    center = image.crop(relative_box(image, 0.25, 0.30, 0.75, 0.72)).convert("L")
    stat = ImageStat.Stat(center)
    pixels = list(center.getdata())
    dark_ratio = sum(1 for value in pixels if 40 <= value <= 95) / max(1, len(pixels))
    mean = stat.mean[0]
    return {
        "modal": dark_ratio >= dark_ratio_limit and mean <= mean_limit,
        "dark_ratio": dark_ratio,
        "mean": mean,
    }


def play_area_sample(image):
    sample = image.crop(relative_box(image, 0.50, 0.28, 0.94, 0.86)).convert("L")
    return sample.resize((96, 96))


def leaderboard_sample(image):
    sample = image.crop(relative_box(image, 0.54, 0.08, 0.99, 0.42)).convert("L")
    return sample.resize((128, 96))


def motion_score(samples):
    if len(samples) < 2:
        return 0
    scores = []
    for previous, current in zip(samples, samples[1:]):
        diff = ImageChops.difference(previous, current)
        scores.append(ImageStat.Stat(diff).mean[0])
    return max(scores) if scores else 0


def tab_response_score(before_image, after_image):
    if not before_image or not after_image:
        return 0
    before = leaderboard_sample(before_image)
    after = leaderboard_sample(after_image)
    diff = ImageChops.difference(before, after)
    return ImageStat.Stat(diff).mean[0]


def roblox_window_health(
    placement,
    hwnd=None,
    sample_count=DEFAULT_DETECTOR_SAMPLE_COUNT,
    sample_delay=DEFAULT_DETECTOR_SAMPLE_DELAY,
    dark_ratio_limit=DEFAULT_DISCONNECT_MODAL_DARK_RATIO,
    mean_limit=DEFAULT_DISCONNECT_MODAL_MEAN_LIMIT,
    min_motion_score=DEFAULT_MIN_ACTIVE_MOTION_SCORE,
    tab_check=True,
    tab_response_limit=MIN_TAB_RESPONSE_SCORE,
):
    if not placement:
        return {"healthy": False, "reason": "window placement is not set", "motion": 0}

    if hwnd:
        focus_window(hwnd)
        time.sleep(0.35)

    capture_rect = resolve_capture_placement(placement, hwnd)
    first_image = capture_window_image(placement, hwnd=hwnd)
    if not first_image:
        return {
            "healthy": False,
            "reason": "could not capture window image",
            "motion": 0,
            "tab_response": 0,
            "capture_rect": capture_rect,
            "modal_dark_ratio": 0,
            "modal_mean": 0,
        }
    modal = disconnect_modal_score(first_image, dark_ratio_limit, mean_limit)
    if modal["modal"]:
        return {
            "healthy": False,
            "reason": "disconnect modal detected",
            "motion": 0,
            "tab_response": 0,
            "capture_rect": capture_rect,
            "modal_dark_ratio": modal["dark_ratio"],
            "modal_mean": modal["mean"],
        }

    tab_response = 0
    if hwnd and tab_check:
        click_inside_window(hwnd)
        time.sleep(0.12)
        before_tab = first_image
        press_key(0x09)
        time.sleep(max(0.35, min(1.2, sample_delay)))
        after_tab = capture_window_image(placement, hwnd=hwnd)
        if not after_tab:
            after_tab = first_image
        modal = disconnect_modal_score(after_tab, dark_ratio_limit, mean_limit)
        if modal["modal"]:
            return {
                "healthy": False,
                "reason": "disconnect modal detected",
                "motion": 0,
                "tab_response": 0,
                "capture_rect": capture_rect,
                "modal_dark_ratio": modal["dark_ratio"],
                "modal_mean": modal["mean"],
            }
        tab_response = tab_response_score(before_tab, after_tab)
        press_key(0x09)
        time.sleep(0.18)
        if tab_response >= tab_response_limit:
            return {
                "healthy": True,
                "reason": "tab response detected",
                "motion": 0,
                "tab_response": tab_response,
                "capture_rect": capture_rect,
                "modal_dark_ratio": modal["dark_ratio"],
                "modal_mean": modal["mean"],
            }
        first_image = capture_window_image(placement, hwnd=hwnd) or first_image

    samples = [play_area_sample(first_image)]
    for _index in range(max(1, sample_count) - 1):
        time.sleep(sample_delay)
        if hwnd:
            focus_window(hwnd)
            time.sleep(0.12)
        image = capture_window_image(placement, hwnd=hwnd)
        if not image:
            return {
                "healthy": False,
                "reason": "could not capture window image",
                "motion": 0,
                "tab_response": tab_response,
                "capture_rect": capture_rect,
                "modal_dark_ratio": modal["dark_ratio"],
                "modal_mean": modal["mean"],
            }
        modal = disconnect_modal_score(image, dark_ratio_limit, mean_limit)
        if modal["modal"]:
            return {
                "healthy": False,
                "reason": "disconnect modal detected",
                "motion": 0,
                "tab_response": tab_response,
                "capture_rect": capture_rect,
                "modal_dark_ratio": modal["dark_ratio"],
                "modal_mean": modal["mean"],
            }
        samples.append(play_area_sample(image))

    motion = motion_score(samples)
    if motion <= min_motion_score:
        return {
            "healthy": False,
            "reason": "screen did not change across samples",
            "motion": motion,
            "tab_response": tab_response,
            "capture_rect": capture_rect,
            "modal_dark_ratio": modal["dark_ratio"],
            "modal_mean": modal["mean"],
        }

    return {
        "healthy": True,
        "reason": "active",
        "motion": motion,
        "tab_response": tab_response,
        "capture_rect": capture_rect,
        "modal_dark_ratio": modal["dark_ratio"],
        "modal_mean": modal["mean"],
    }


def kill_process(pid):
    if os.name != "nt" or not pid:
        return
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/F"],
        capture_output=True,
        text=True,
        creationflags=hidden_process_flags(),
    )


class RobloxMultiInstanceLock:
    def __init__(self):
        self.thread = None
        self.ready_event = threading.Event()
        self.release_event = threading.Event()
        self.error = None

    def acquire(self):
        if os.name != "nt":
            return
        if self.thread and self.thread.is_alive():
            return

        self.ready_event.clear()
        self.release_event.clear()
        self.error = None
        self.thread = threading.Thread(target=self._hold_lock, daemon=True)
        self.thread.start()
        if not self.ready_event.wait(6):
            raise RuntimeError("Timed out while starting the Roblox multi-instance lock.")
        if self.error:
            raise RuntimeError(self.error)

    def _hold_lock(self):
        handle = None
        acquired = False
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.CreateMutexW.restype = wintypes.HANDLE
            kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
            kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel32.WaitForSingleObject.restype = wintypes.DWORD
            handle = kernel32.CreateMutexW(None, False, ROBLOX_MULTI_MUTEX)
            if not handle:
                raise ctypes.WinError()

            wait_result = kernel32.WaitForSingleObject(handle, 5000)
            if wait_result not in (WAIT_OBJECT_0, WAIT_ABANDONED):
                raise RuntimeError("Could not acquire the Roblox multi-instance lock.")

            acquired = True
            self.ready_event.set()
            self.release_event.wait()
        except Exception as exc:
            self.error = str(exc)
            self.ready_event.set()
        finally:
            if handle:
                if acquired:
                    ctypes.windll.kernel32.ReleaseMutex(handle)
                ctypes.windll.kernel32.CloseHandle(handle)

    def release(self):
        if os.name != "nt" or not self.thread:
            return
        self.release_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=3)
        self.thread = None


def build_protocol_launch_uri(auth_ticket, place_id, private_code="", private_link_code="", browser_tracker_id=None):
    browser_tracker_id = browser_tracker_id or str(secrets.randbelow(800_000_000_000) + 100_000_000_000)
    launch_time = int(time.time() * 1000)
    if private_code:
        join_url = (
            "https://assetgame.roblox.com/game/PlaceLauncher.ashx"
            f"?request=RequestPrivateGame&placeId={urllib.parse.quote(str(place_id))}"
            f"&accessCode={urllib.parse.quote(str(private_code))}"
            f"&linkCode={urllib.parse.quote(str(private_link_code or ''))}"
        )
    else:
        join_url = (
            "https://assetgame.roblox.com/game/PlaceLauncher.ashx"
            f"?request=RequestGame&browserTrackerId={browser_tracker_id}"
            f"&placeId={urllib.parse.quote(str(place_id))}"
            "&isPlayTogetherGame=false"
        )
    return (
        "roblox-player:1"
        f"+launchmode:play"
        f"+gameinfo:{auth_ticket}"
        f"+launchtime:{launch_time}"
        f"+placelauncherurl:{urllib.parse.quote(join_url, safe='')}"
        f"+browsertrackerid:{browser_tracker_id}"
        "+robloxLocale:en_us"
        "+gameLocale:en_us"
        "+channel:"
        "+LaunchExp:InApp"
    )


def start_roblox_player(auth_ticket, place_id, private_code="", private_link_code=""):
    if not find_roblox_player():
        raise RuntimeError("Roblox Player was not found.")
    uri = build_protocol_launch_uri(auth_ticket, place_id, private_code, private_link_code)
    os.startfile(uri)


def normalize_roblox_cookie(value):
    cookie = (value or "").strip()
    if not cookie:
        return ""
    match = re.search(r"\.ROBLOSECURITY\s*=\s*([^;\s]+)", cookie, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return cookie.strip().strip('"').strip("'")


def decode_http_body(raw, headers):
    encoding = (headers.get("Content-Encoding") or "").lower()
    try:
        if "gzip" in encoding:
            raw = gzip.decompress(raw)
        elif "deflate" in encoding:
            raw = zlib.decompress(raw)
    except Exception:
        pass
    return raw.decode("utf-8", errors="replace")


def roblox_http_request(url, method="GET", cookie="", headers=None, body=None):
    request_headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate",
    }
    session_cookie = normalize_roblox_cookie(cookie)
    if session_cookie:
        request_headers["Cookie"] = f".ROBLOSECURITY={session_cookie}"
    if headers:
        request_headers.update(headers)
    data = body.encode("utf-8") if isinstance(body, str) else body
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.headers, decode_http_body(response.read(), response.headers)
    except urllib.error.HTTPError as error:
        return error.code, error.headers, decode_http_body(error.read(), error.headers)


def get_authentication_ticket_from_cookie(cookie):
    url = "https://auth.roblox.com/v1/authentication-ticket"
    headers = {
        "Content-Type": "application/json",
        "Referer": "https://www.roblox.com/games/4924922222/Brookhaven-RP",
    }
    status, response_headers, text = roblox_http_request(url, "POST", cookie, headers, "{}")
    csrf = response_headers.get("x-csrf-token")
    if status == 403 and csrf:
        headers["X-CSRF-TOKEN"] = csrf
        status, response_headers, text = roblox_http_request(url, "POST", cookie, headers, "{}")

    ticket = response_headers.get("rbx-authentication-ticket")
    if ticket:
        return ticket
    raise RuntimeError(f"Could not get Roblox authentication ticket from saved session (HTTP {status}): {text[:240]}")


def resolve_private_server_access_code_from_cookie(cookie, place_id, private_link_code):
    if not private_link_code:
        return ""
    url = (
        "https://www.roblox.com/games/"
        f"{urllib.parse.quote(str(place_id))}?privateServerLinkCode={urllib.parse.quote(str(private_link_code))}"
    )
    status, _headers, text = roblox_http_request(
        url,
        "GET",
        cookie,
        {"Referer": "https://www.roblox.com/games/4924922222/Brookhaven-RP"},
    )
    match = re.search(r"Roblox\.GameLauncher\.joinPrivateGame\(\d+,\s*'([\w-]+)'", text)
    if match:
        return match.group(1)
    raise RuntimeError(f"Could not resolve private server link from saved session (HTTP {status}).")


def validate_roblox_session_cookie(cookie, target_url=""):
    session_cookie = normalize_roblox_cookie(cookie)
    if not session_cookie:
        raise RuntimeError("No session cookie is saved for this account.")

    status, _headers, text = roblox_http_request("https://www.roblox.com/my/account/json", "GET", session_cookie)
    try:
        data = json.loads(text)
    except Exception:
        data = {}
    username = data.get("Name") or data.get("name") or "Roblox account"
    user_id = data.get("UserId") or data.get("userId")
    if status != 200 or not user_id:
        raise RuntimeError(f"Saved session cookie is not valid (HTTP {status}).")

    place_id, private_code = parse_roblox_server_url(target_url) if target_url else ("", "")
    if place_id and private_code:
        resolve_private_server_access_code_from_cookie(session_cookie, place_id, private_code)
    return {"username": username, "user_id": user_id}


def launch_server_with_cookie(target_url, session_cookie, stop_existing=True):
    place_id, private_code = parse_roblox_server_url(target_url)
    if not place_id:
        raise RuntimeError("Could not find a Roblox place ID in the server URL.")
    if stop_existing and is_roblox_running():
        stop_roblox()

    auth_ticket = get_authentication_ticket_from_cookie(session_cookie)
    access_code = resolve_private_server_access_code_from_cookie(session_cookie, place_id, private_code) if private_code else ""
    start_roblox_player(auth_ticket, place_id, access_code, private_code)
    return {"browser": "session", "status": "launch_requested"}


class DevToolsConnection:
    def __init__(self, websocket_url, timeout=120):
        parsed = urllib.parse.urlparse(websocket_url)
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or 80
        self.path = parsed.path
        if parsed.query:
            self.path += "?" + parsed.query
        self.sock = socket.create_connection((self.host, self.port), timeout=timeout)
        self.sock.settimeout(timeout)
        self.next_id = 1
        self._handshake()

    def _handshake(self):
        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        request = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(request.encode("ascii"))
        response = self.sock.recv(4096)
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise RuntimeError("Chrome DevTools websocket handshake failed.")

    def _recv_exact(self, size):
        chunks = []
        remaining = size
        while remaining:
            chunk = self.sock.recv(remaining)
            if not chunk:
                raise RuntimeError("Chrome DevTools websocket closed.")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def send_json(self, message):
        payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.extend([0x80 | 126, (length >> 8) & 0xFF, length & 0xFF])
        else:
            header.append(0x80 | 127)
            header.extend(length.to_bytes(8, "big"))
        mask = secrets.token_bytes(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def receive_json(self):
        while True:
            first, second = self._recv_exact(2)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = int.from_bytes(self._recv_exact(2), "big")
            elif length == 127:
                length = int.from_bytes(self._recv_exact(8), "big")
            mask = self._recv_exact(4) if masked else b""
            payload = self._recv_exact(length)
            if masked:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            if opcode == 8:
                raise RuntimeError("Chrome DevTools websocket closed.")
            if opcode == 1:
                return json.loads(payload.decode("utf-8"))

    def call(self, method, params=None):
        request_id = self.next_id
        self.next_id += 1
        self.send_json({"id": request_id, "method": method, "params": params or {}})
        while True:
            message = self.receive_json()
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(message["error"].get("message", "Chrome DevTools command failed."))
                return message.get("result", {})

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


def wait_for_debug_target(port, timeout=20):
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=1) as response:
                targets = json.loads(response.read().decode("utf-8"))
            for target in targets:
                if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
                    return target
        except Exception as exc:
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"Could not connect to browser automation: {last_error}")


def runtime_evaluate(connection, params, attempts=30):
    last_error = None
    for _attempt in range(attempts):
        try:
            return connection.call("Runtime.evaluate", params)
        except RuntimeError as exc:
            last_error = exc
            text = str(exc)
            if (
                "Cannot find default execution context" in text
                or "Execution context was destroyed" in text
                or "Inspected target navigated" in text
            ):
                time.sleep(0.25)
                continue
            raise
    raise RuntimeError(str(last_error) if last_error else "Runtime evaluation failed.")


def wait_for_page_ready(connection, timeout=45):
    expression = """
    (async () => {
        const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
        for (let attempt = 0; attempt < 180; attempt += 1) {
            if (document.readyState === "complete" || document.readyState === "interactive") {
                return { ok: true, url: location.href };
            }
            await sleep(250);
        }
        return { ok: false, url: location.href };
    })()
    """
    return runtime_evaluate(
        connection,
        {"expression": expression, "awaitPromise": True, "returnByValue": True, "timeout": timeout * 1000},
    )


def roblox_api_login(connection, username, password):
    expression = f"""
    (async () => {{
        const payload = {{
            ctype: "Username",
            cvalue: {json.dumps(username)},
            password: {json.dumps(password)}
        }};

        const send = async (csrf) => {{
            const headers = {{ "Content-Type": "application/json" }};
            if (csrf) headers["x-csrf-token"] = csrf;
            const response = await fetch("https://auth.roblox.com/v2/login", {{
                method: "POST",
                credentials: "include",
                headers,
                body: JSON.stringify(payload)
            }});
            const text = await response.text();
            return {{
                ok: response.ok,
                status: response.status,
                csrf: response.headers.get("x-csrf-token") || "",
                challengeId: response.headers.get("rblx-challenge-id") || "",
                challengeType: response.headers.get("rblx-challenge-type") || "",
                text: text.slice(0, 1200)
            }};
        }};

        let result = await send("");
        if (result.status === 403 && result.csrf) {{
            result = await send(result.csrf);
        }}
        return result;
    }})()
    """
    result = runtime_evaluate(
        connection,
        {"expression": expression, "awaitPromise": True, "returnByValue": True},
    )
    value = result.get("result", {}).get("value", {})
    if value.get("ok"):
        return value
    if value.get("challengeType"):
        raise RuntimeError(f"Roblox asked for {value['challengeType']} verification.")
    detail = value.get("text", "").strip()
    raise RuntimeError(f"Roblox login failed with HTTP {value.get('status')}: {detail[:240]}")


def get_authentication_ticket(connection):
    expression = """
    (async () => {
        const send = async (csrf) => {
            const headers = { "Content-Type": "application/json" };
            if (csrf) headers["x-csrf-token"] = csrf;
            const response = await fetch("https://auth.roblox.com/v1/authentication-ticket", {
                method: "POST",
                credentials: "include",
                headers,
                body: "{}"
            });
            const text = await response.text();
            return {
                ok: response.ok,
                status: response.status,
                csrf: response.headers.get("x-csrf-token") || "",
                ticket: response.headers.get("rbx-authentication-ticket") || "",
                text: text.slice(0, 600)
            };
        };

        let result = await send("");
        if (result.status === 403 && result.csrf) {
            result = await send(result.csrf);
        }
        return result;
    })()
    """
    result = runtime_evaluate(
        connection,
        {"expression": expression, "awaitPromise": True, "returnByValue": True},
    )
    value = result.get("result", {}).get("value", {})
    if value.get("ticket"):
        return value["ticket"]
    detail = value.get("text", "").strip()
    raise RuntimeError(f"Could not get Roblox authentication ticket (HTTP {value.get('status')}): {detail[:240]}")


def resolve_private_server_access_code(connection, place_id, private_link_code):
    if not private_link_code:
        return ""

    game_url = f"https://www.roblox.com/games/{urllib.parse.quote(str(place_id))}?privateServerLinkCode={urllib.parse.quote(str(private_link_code))}"
    expression = f"""
    (async () => {{
        const response = await fetch({json.dumps(game_url)}, {{
            method: "GET",
            credentials: "include",
            redirect: "follow",
            headers: {{ "Accept": "text/html,application/xhtml+xml" }}
        }});
        const text = await response.text();
        return {{
            ok: response.ok,
            status: response.status,
            url: response.url,
            text: text.slice(0, 120000)
        }};
    }})()
    """
    result = runtime_evaluate(
        connection,
        {"expression": expression, "awaitPromise": True, "returnByValue": True, "timeout": 45000},
    )
    value = result.get("result", {}).get("value", {})
    text = value.get("text", "")
    match = re.search(r"Roblox\.GameLauncher\.joinPrivateGame\(\d+,\s*'([\w-]+)'", text)
    if match:
        return match.group(1)

    if value.get("status") in (401, 403):
        raise RuntimeError("Roblox would not resolve the private server link for this logged-in account.")
    raise RuntimeError("Could not resolve the Roblox private server access code from the server link.")


def launch_server_background(
    target_url,
    username,
    password,
    session_cookie="",
    close_when_roblox_opens=True,
    stop_existing=True,
    wait_for_player=False,
):
    if session_cookie:
        return launch_server_with_cookie(target_url, normalize_roblox_cookie(session_cookie), stop_existing=stop_existing)

    browsers = automated_browser_candidates()
    if not browsers:
        raise RuntimeError("Chrome or Edge was not found.")
    place_id, private_code = parse_roblox_server_url(target_url)
    if not place_id:
        raise RuntimeError("Could not find a Roblox place ID in the server URL.")

    if stop_existing and is_roblox_running():
        stop_roblox()

    browser = browsers[0]
    port = free_local_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="server-launcher-profile-"))
    process = subprocess.Popen(
        [
            str(browser),
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--disable-extensions",
            "--window-size=1000,800",
            "--window-position=-32000,-32000",
            "--new-window",
            roblox_login_url(target_url),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=hidden_process_flags(),
    )

    connection = None
    status = "started"
    try:
        target = wait_for_debug_target(port)
        connection = DevToolsConnection(target["webSocketDebuggerUrl"])
        connection.call("Runtime.enable")
        wait_for_page_ready(connection)
        try:
            roblox_api_login(connection, username, password)
            status = "logged_in"
        except RuntimeError as exc:
            if "proofofwork" not in str(exc).lower():
                raise
            raise RuntimeError(
                "Roblox blocked password login with proof-of-work verification. "
                "Add this account's Roblox session cookie in Settings to use the reliable launch path."
            )
        auth_ticket = get_authentication_ticket(connection)
        access_code = resolve_private_server_access_code(connection, place_id, private_code) if private_code else ""
        status = "launching_player"
        initial_roblox_count = roblox_process_count()
        start_roblox_player(auth_ticket, place_id, access_code, private_code)

        if wait_for_player:
            deadline = time.time() + 45
            while time.time() < deadline:
                if roblox_process_count() > initial_roblox_count:
                    status = "roblox_started"
                    break
                time.sleep(1)
            else:
                status = "player_start_requested"
        else:
            status = "launch_requested"

        return {"browser": browser.name, "status": status}
    finally:
        if connection:
            connection.close()
        if close_when_roblox_opens or status == "started":
            try:
                process.terminate()
            except Exception:
                pass

        def cleanup():
            try:
                process.wait(timeout=8)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
            shutil.rmtree(profile_dir, ignore_errors=True)

        threading.Thread(target=cleanup, daemon=True).start()


def next_switch_time(hour, minute, now=None):
    now = now or dt.datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return target


def format_timedelta(delta):
    total = max(0, int(delta.total_seconds()))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def build_diagnostics_report(snapshot):
    lines = ["Collect All Pets Launcher Diagnostics", ""]
    issue_count = 0
    warning_count = 0

    def add(kind, text):
        nonlocal issue_count, warning_count
        if kind == "ISSUE":
            issue_count += 1
        elif kind == "WARN":
            warning_count += 1
        lines.append(f"{kind}: {text}")

    player = find_roblox_player()
    if player:
        add("OK", f"Roblox Player found: {player}")
    else:
        add("ISSUE", "Roblox Player was not found. Install or repair Roblox Player before launching.")

    browsers = automated_browser_candidates()
    if browsers:
        add("OK", f"Automation browser found: {browsers[0].name}")
    else:
        add("ISSUE", "Chrome or Edge was not found. Cookie capture and fallback login need one of them.")

    for label, url in (("Server 1", snapshot.get("server_one", "")), ("Server 2", snapshot.get("server_two", ""))):
        if not url:
            add("ISSUE", f"{label} URL is empty.")
            continue
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.lower()
        place_id, private_code = parse_roblox_server_url(url)
        if "roblox.com" not in host:
            add("WARN", f"{label} URL does not look like a roblox.com link.")
        if not place_id:
            add("ISSUE", f"{label} URL does not include a Roblox place ID.")
        elif private_code:
            add("OK", f"{label} URL parsed: place {place_id}, private server link detected.")
        else:
            add("OK", f"{label} URL parsed: place {place_id}.")

    accounts = snapshot.get("accounts", [])
    enabled_accounts = [account for account in accounts if account.get("enabled")]
    cookie_accounts = [account for account in enabled_accounts if account.get("session_cookie")]
    add("OK", f"Accounts configured: {len(accounts)} total, {len(enabled_accounts)} enabled.")
    if not enabled_accounts:
        add("ISSUE", "No accounts are enabled.")

    if len(enabled_accounts) > 1:
        if os.name == "nt":
            add("OK", "Multiple enabled accounts detected; multi-instance lock is available.")
        else:
            add("ISSUE", "Multiple accounts need the Roblox multi-instance lock, which is Windows-only.")

    if enabled_accounts and not cookie_accounts:
        add(
            "ISSUE",
            "No enabled account has a saved session cookie. Roblox is currently blocking hidden password login with proof-of-work, so use Capture Cookie for each enabled account.",
        )

    for account in accounts:
        label = f"Account {account.get('index')}"
        username = account.get("username") or "(no username)"
        if not account.get("enabled"):
            add("OK", f"{label} is off; skipping launch checks.")
            continue
        if not account.get("username"):
            add("ISSUE", f"{label} is on but has no username.")
        if not account.get("has_password") and not account.get("session_cookie"):
            add("ISSUE", f"{label} ({username}) needs a password or session cookie.")
        elif account.get("has_password") and not account.get("session_cookie"):
            add("WARN", f"{label} ({username}) is password-only; Capture Cookie is recommended for reliable launch.")
        if account.get("placement"):
            placement = account["placement"]
            add(
                "OK",
                f"{label} ({username}) placement saved: {placement.get('x')}, {placement.get('y')} {placement.get('width')}x{placement.get('height')}.",
            )
        else:
            add("WARN", f"{label} ({username}) has no saved Roblox window placement; keep alive cannot target it yet.")

    current_url = snapshot.get("current_url", "")
    for account in cookie_accounts:
        label = f"Account {account.get('index')}"
        username = account.get("username") or label
        try:
            result = validate_roblox_session_cookie(account.get("session_cookie", ""), current_url)
            add("OK", f"{label} session cookie is valid for {result.get('username') or username}.")
        except Exception as exc:
            add("ISSUE", f"{label} session cookie failed validation: {exc}")

    try:
        keep_alive_minutes = int(snapshot.get("keep_alive_minutes") or DEFAULT_KEEP_ALIVE_MINUTES)
    except Exception:
        keep_alive_minutes = DEFAULT_KEEP_ALIVE_MINUTES
    add(
        "OK",
        f"Keep alive is {'on' if snapshot.get('keep_alive') else 'off'}; interval is {keep_alive_minutes} minute(s).",
    )
    detector = snapshot.get("detector", {})
    if detector:
        add(
            "OK",
            "Disconnect sensor configured: "
            f"{detector.get('sample_count')} photos, {detector.get('sample_delay')}s pause.",
        )
    add("OK", f"Auto switch is {'on' if snapshot.get('auto_rotate') else 'off'}.")

    running_windows = enum_roblox_windows()
    if running_windows:
        add("OK", f"Roblox windows currently visible: {len(running_windows)}.")
    else:
        add("WARN", "No visible Roblox windows were detected right now.")

    lines.append("")
    if issue_count:
        lines.append(f"Result: {issue_count} issue(s), {warning_count} warning(s).")
    elif warning_count:
        lines.append(f"Result: passed with {warning_count} warning(s).")
    else:
        lines.append("Result: passed.")
    return "\n".join(lines), issue_count, warning_count


class ServerLauncher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Collect All Pets Server Switcher")
        self.geometry("980x760")
        self.minsize(900, 700)

        self.server_one_var = tk.StringVar()
        self.server_two_var = tk.StringVar()
        self.current_server_var = tk.IntVar(value=1)
        self.switch_hour_var = tk.StringVar(value="07")
        self.switch_minute_var = tk.StringVar(value="00")
        self.auto_rotate_var = tk.BooleanVar(value=True)
        self.keep_alive_var = tk.BooleanVar(value=False)
        self.keep_alive_minutes_var = tk.IntVar(value=DEFAULT_KEEP_ALIVE_MINUTES)
        self.detector_popup_sensitivity_var = tk.IntVar(value=DEFAULT_POPUP_SENSITIVITY)
        self.detector_activity_sensitivity_var = tk.IntVar(value=DEFAULT_ACTIVITY_SENSITIVITY)
        self.detector_sample_count_var = tk.IntVar(value=DEFAULT_DETECTOR_SAMPLE_COUNT)
        self.detector_sample_delay_var = tk.DoubleVar(value=DEFAULT_DETECTOR_SAMPLE_DELAY)
        self.status_var = tk.StringVar(value="Ready.")
        self.countdown_var = tk.StringVar(value="Next switch: --")
        self.keep_alive_countdown_var = tk.StringVar(value="Keep alive: --")
        self.active_server_var = tk.StringVar(value="Current server: Server 1")
        self.readiness_var = tk.StringVar(value="Checking launcher setup...")
        self.readiness_label = None
        self.launch_in_progress = False
        self.keep_alive_in_progress = False
        self.keep_alive_after_id = None
        self.next_keep_alive = None
        self.next_switch = None
        self.last_switch_key = None
        self.account_rows = []
        self.multi_instance_lock = RobloxMultiInstanceLock()

        self._build_ui()
        self._load_settings()
        self._refresh_schedule()
        self._refresh_readiness()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(1000, self._tick)
        self._schedule_keep_alive_tick()

    def _build_ui(self):
        self.configure(bg=COLOR_BG)
        self.option_add("*Font", ("Segoe UI", 11))
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 11))
        style.configure("App.TFrame", background=COLOR_BG)
        style.configure("Surface.TFrame", background=COLOR_SURFACE)
        style.configure("Card.TFrame", background=COLOR_CARD, borderwidth=1, relief="solid")
        style.configure("TFrame", background=COLOR_SURFACE)
        style.configure("TLabel", background=COLOR_SURFACE, foreground=COLOR_TEXT)
        style.configure("Hero.TLabel", background=COLOR_BG, foreground="#ffffff", font=("Segoe UI Semibold", 26))
        style.configure("HeroSub.TLabel", background=COLOR_BG, foreground="#cbd5e1", font=("Segoe UI", 11))
        style.configure("Title.TLabel", background=COLOR_SURFACE, foreground=COLOR_TEXT, font=("Segoe UI Semibold", 17))
        style.configure("Metric.TLabel", background=COLOR_SURFACE, foreground=COLOR_TEXT, font=("Segoe UI Semibold", 14))
        style.configure("Muted.TLabel", background=COLOR_SURFACE, foreground=COLOR_MUTED, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT)
        style.configure("CardTitle.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT, font=("Segoe UI Semibold", 12))
        style.configure("CardMuted.TLabel", background=COLOR_CARD, foreground=COLOR_MUTED, font=("Segoe UI", 10))
        style.configure("Status.TLabel", background=COLOR_CARD, foreground=COLOR_MUTED, font=("Segoe UI", 10))
        style.configure("TButton", padding=(12, 8), font=("Segoe UI Semibold", 10))
        style.configure("Primary.TButton", background=COLOR_PRIMARY, foreground="#ffffff", bordercolor=COLOR_PRIMARY, focusthickness=0)
        style.map("Primary.TButton", background=[("active", COLOR_PRIMARY_DARK), ("pressed", COLOR_PRIMARY_DARK)])
        style.configure("Secondary.TButton", background="#e2e8f0", foreground=COLOR_TEXT, bordercolor="#cbd5e1", focusthickness=0)
        style.map("Secondary.TButton", background=[("active", "#cbd5e1"), ("pressed", "#cbd5e1")])
        style.configure("Danger.TButton", background=COLOR_DANGER, foreground="#ffffff", bordercolor=COLOR_DANGER, focusthickness=0)
        style.map("Danger.TButton", background=[("active", COLOR_DANGER_DARK), ("pressed", COLOR_DANGER_DARK)])
        style.configure("TCheckbutton", background=COLOR_SURFACE, foreground=COLOR_TEXT)
        style.configure("Card.TCheckbutton", background=COLOR_CARD, foreground=COLOR_TEXT)
        style.configure("TEntry", padding=(8, 6), fieldbackground="#ffffff", bordercolor=COLOR_BORDER)
        style.configure("TSpinbox", padding=(8, 6), fieldbackground="#ffffff", bordercolor=COLOR_BORDER)

        root = ttk.Frame(self, padding=(22, 18), style="App.TFrame")
        root.pack(fill="both", expand=True)

        tk.Label(
            root,
            text="Collect All Pets",
            bg=COLOR_BG,
            fg="#ffffff",
            font=("Segoe UI Semibold", 24),
        ).pack(anchor="w")
        tk.Label(
            root,
            text="Launcher Console",
            bg=COLOR_BG,
            fg="#cbd5e1",
            font=("Segoe UI", 11),
        ).pack(anchor="w", pady=(2, 16))

        surface = ttk.Frame(root, padding=16, style="Surface.TFrame")
        surface.pack(fill="both", expand=True)

        nav = ttk.Frame(surface, style="Surface.TFrame")
        nav.pack(fill="x", pady=(0, 14))
        self.nav_buttons = {
            "control": self.modern_button(nav, "Control", lambda: self.show_view("control"), "primary"),
            "testing": self.modern_button(nav, "Testing", lambda: self.show_view("testing"), "secondary"),
            "settings": self.modern_button(nav, "Settings", lambda: self.show_view("settings"), "secondary"),
        }
        self.nav_buttons["control"].pack(side="left", padx=(0, 8))
        self.nav_buttons["testing"].pack(side="left", padx=(0, 8))
        self.nav_buttons["settings"].pack(side="left")

        self.content_frame = ttk.Frame(surface, style="Surface.TFrame")
        self.content_frame.pack(fill="both", expand=True)
        self.content_frame.columnconfigure(0, weight=1)
        self.content_frame.rowconfigure(0, weight=1)

        control = ttk.Frame(self.content_frame, padding=18, style="Surface.TFrame")
        testing = ttk.Frame(self.content_frame, padding=18, style="Surface.TFrame")
        settings = ttk.Frame(self.content_frame, padding=18, style="Surface.TFrame")
        self.views = {"control": control, "testing": testing, "settings": settings}
        self._build_control_tab(control)
        self._build_testing_tab(testing)
        self._build_settings_tab(settings)
        self.show_view("control")

    def modern_button(self, parent, text, command, variant="secondary", width=None):
        palette = {
            "primary": (COLOR_PRIMARY, COLOR_PRIMARY_DARK, "#ffffff"),
            "secondary": ("#e2e8f0", "#cbd5e1", COLOR_TEXT),
            "danger": (COLOR_DANGER, COLOR_DANGER_DARK, "#ffffff"),
        }
        bg, active_bg, fg = palette.get(variant, palette["secondary"])
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=active_bg,
            activeforeground=fg,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=16,
            pady=10,
            cursor="hand2",
            font=("Segoe UI Semibold", 10),
        )
        if width:
            button.configure(width=width)
        return button

    def modern_toggle(self, parent, text, variable, command=None, card=False, width=None):
        toggle = tk.Checkbutton(
            parent,
            text=text,
            variable=variable,
            indicatoron=False,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=12,
            pady=8,
            cursor="hand2",
            font=("Segoe UI Semibold", 10),
        )
        if width:
            toggle.configure(width=width)

        def refresh():
            selected = bool(variable.get())
            toggle.configure(
                bg=COLOR_PRIMARY if selected else "#e2e8f0",
                fg="#ffffff" if selected else COLOR_TEXT,
                activebackground=COLOR_PRIMARY_DARK if selected else "#cbd5e1",
                activeforeground="#ffffff" if selected else COLOR_TEXT,
                selectcolor=COLOR_PRIMARY if selected else "#e2e8f0",
            )

        def clicked():
            refresh()
            if command:
                command()

        toggle.configure(command=clicked)
        try:
            variable.trace_add("write", lambda *_args: refresh())
        except Exception:
            pass
        refresh()
        return toggle

    def set_button_variant(self, button, variant):
        palette = {
            "primary": (COLOR_PRIMARY, COLOR_PRIMARY_DARK, "#ffffff"),
            "secondary": ("#e2e8f0", "#cbd5e1", COLOR_TEXT),
            "danger": (COLOR_DANGER, COLOR_DANGER_DARK, "#ffffff"),
        }
        bg, active_bg, fg = palette.get(variant, palette["secondary"])
        button.configure(bg=bg, fg=fg, activebackground=active_bg, activeforeground=fg)

    def show_view(self, name):
        self._refresh_readiness()
        for key, frame in self.views.items():
            frame.grid_forget()
            if hasattr(self, "nav_buttons"):
                self.set_button_variant(self.nav_buttons[key], "primary" if key == name else "secondary")
        self.views[name].grid(row=0, column=0, sticky="nsew")

    def _build_control_tab(self, parent):
        parent.columnconfigure(1, weight=1)
        tk.Label(
            parent,
            textvariable=self.active_server_var,
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            font=("Segoe UI Black", 21),
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))

        readiness_card = tk.Frame(parent, bg="#eff6ff", highlightbackground="#bfdbfe", highlightthickness=1)
        readiness_card.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 14))
        readiness_card.columnconfigure(0, weight=1)
        tk.Label(
            readiness_card,
            text="Launch readiness",
            bg="#eff6ff",
            fg=COLOR_PRIMARY_DARK,
            font=("Segoe UI Semibold", 10),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
        self.readiness_label = tk.Label(
            readiness_card,
            textvariable=self.readiness_var,
            bg="#eff6ff",
            fg=COLOR_TEXT,
            font=("Segoe UI", 10),
            anchor="w",
            justify="left",
            wraplength=820,
        )
        self.readiness_label.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))

        ttk.Label(parent, text="Daily switch time").grid(row=2, column=0, sticky="w", pady=8)
        schedule_frame = ttk.Frame(parent, style="Surface.TFrame")
        schedule_frame.grid(row=2, column=1, rowspan=2, sticky="w", pady=8)
        time_inputs = ttk.Frame(schedule_frame, style="Surface.TFrame")
        time_inputs.grid(row=0, column=0, sticky="w")
        ttk.Spinbox(time_inputs, from_=0, to=23, width=4, textvariable=self.switch_hour_var, format="%02.0f", command=self._refresh_schedule).pack(side="left")
        ttk.Label(time_inputs, text=":").pack(side="left", padx=4)
        ttk.Spinbox(time_inputs, from_=0, to=59, width=4, textvariable=self.switch_minute_var, format="%02.0f", command=self._refresh_schedule).pack(side="left")
        self.modern_button(schedule_frame, "Set Time", self.set_switch_time, "secondary", width=10).grid(row=0, column=1, sticky="w", padx=(10, 0))
        toggle_frame = ttk.Frame(parent, style="Surface.TFrame")
        toggle_frame.grid(row=2, column=2, columnspan=2, sticky="w", padx=(18, 0), pady=8)
        self.modern_toggle(toggle_frame, "Auto switch daily", self.auto_rotate_var, self._save_settings, width=18).pack(side="left", padx=(0, 10))
        self.modern_toggle(toggle_frame, "Keep alive", self.keep_alive_var, self.keep_alive_toggled, width=18).pack(side="left")

        ttk.Label(parent, text="Keep alive minutes").grid(row=3, column=0, sticky="w", pady=(2, 6))
        ttk.Spinbox(
            schedule_frame,
            from_=1,
            to=120,
            width=5,
            textvariable=self.keep_alive_minutes_var,
            command=self._save_settings,
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.modern_button(schedule_frame, "Reset", self.reset_keep_alive_timer, "secondary", width=10).grid(row=1, column=1, sticky="w", padx=(10, 0), pady=(8, 0))
        ttk.Label(parent, textvariable=self.keep_alive_countdown_var).grid(row=4, column=0, columnspan=4, sticky="w", pady=(2, 4))
        ttk.Label(parent, textvariable=self.countdown_var).grid(row=5, column=0, columnspan=4, sticky="w", pady=(0, 18))

        action_frame = ttk.Frame(parent, style="Surface.TFrame")
        action_frame.grid(row=6, column=0, columnspan=4, sticky="w", pady=8)
        button_width = 18
        self.modern_button(action_frame, "Launch Server 1", lambda: self.launch_server(1), "primary", width=button_width).pack(side="left", padx=(0, 10))
        self.modern_button(action_frame, "Launch Server 2", lambda: self.launch_server(2), "primary", width=button_width).pack(side="left", padx=(0, 10))
        self.modern_button(action_frame, "Switch Now", self.switch_now, "secondary", width=button_width).pack(side="left", padx=(0, 10))
        self.modern_button(action_frame, "Stop Roblox", self.stop_roblox_from_ui, "danger", width=button_width).pack(side="left")

        ttk.Separator(parent).grid(row=7, column=0, columnspan=4, sticky="ew", pady=18)
        status_card = ttk.Frame(parent, padding=14, style="Card.TFrame")
        status_card.grid(row=8, column=0, columnspan=4, sticky="ew")
        status_card.columnconfigure(0, weight=1)
        ttk.Label(status_card, text="Status", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(status_card, textvariable=self.status_var, style="Status.TLabel", wraplength=740).grid(row=1, column=0, sticky="w", pady=(4, 0))

    def _build_testing_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        tk.Label(
            parent,
            text="Testing",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            font=("Segoe UI Black", 21),
        ).grid(row=0, column=0, sticky="w", pady=(0, 18))

        action_frame = ttk.Frame(parent, style="Surface.TFrame")
        action_frame.grid(row=1, column=0, sticky="w", pady=8)
        button_width = 20
        self.modern_button(action_frame, "Test Keystrokes", self.test_keep_alive_keys, "secondary", width=button_width).pack(side="left", padx=(0, 10))
        self.modern_button(action_frame, "Test Alive Check", self.test_alive_check, "secondary", width=button_width).pack(side="left", padx=(0, 10))
        self.modern_button(action_frame, "Reposition Windows", self.reposition_windows, "secondary", width=button_width).pack(side="left", padx=(0, 10))
        self.modern_button(action_frame, "Run Diagnostics", self.run_diagnostics, "secondary", width=button_width).pack(side="left")

        ttk.Separator(parent).grid(row=2, column=0, sticky="ew", pady=18)
        tuning_card = ttk.Frame(parent, padding=14, style="Card.TFrame")
        tuning_card.grid(row=3, column=0, sticky="ew")
        tuning_card.columnconfigure(1, weight=1)
        ttk.Label(tuning_card, text="Disconnect Sensor", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        self.add_detector_slider(
            tuning_card,
            row=1,
            label="Popup sensitivity",
            variable=self.detector_popup_sensitivity_var,
            from_=0,
            to=100,
        )
        self.add_detector_slider(
            tuning_card,
            row=2,
            label="Activity sensitivity",
            variable=self.detector_activity_sensitivity_var,
            from_=0,
            to=100,
        )
        self.add_detector_slider(
            tuning_card,
            row=3,
            label="Photos per check",
            variable=self.detector_sample_count_var,
            from_=2,
            to=6,
            resolution=1,
        )
        self.add_detector_slider(
            tuning_card,
            row=4,
            label="Pause between photos",
            variable=self.detector_sample_delay_var,
            from_=0.5,
            to=3.0,
            resolution=0.25,
        )

        ttk.Separator(parent).grid(row=4, column=0, sticky="ew", pady=18)
        status_card = ttk.Frame(parent, padding=14, style="Card.TFrame")
        status_card.grid(row=5, column=0, sticky="ew")
        status_card.columnconfigure(0, weight=1)
        ttk.Label(status_card, text="Status", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(status_card, textvariable=self.status_var, style="Status.TLabel", wraplength=820).grid(row=1, column=0, sticky="w", pady=(4, 0))

    def add_detector_slider(self, parent, row, label, variable, from_, to, resolution=1):
        ttk.Label(parent, text=label, style="CardMuted.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 14), pady=8)
        slider = tk.Scale(
            parent,
            variable=variable,
            from_=from_,
            to=to,
            orient="horizontal",
            resolution=resolution,
            showvalue=False,
            bg=COLOR_CARD,
            highlightthickness=0,
            troughcolor="#dbeafe",
            activebackground=COLOR_PRIMARY,
            command=lambda _value: self._detector_setting_changed(save=False),
        )
        slider.grid(row=row, column=1, sticky="ew", pady=8)
        slider.bind("<ButtonRelease-1>", lambda _event: self._detector_setting_changed(save=True))
        slider.bind("<KeyRelease>", lambda _event: self._detector_setting_changed(save=True))

    def _build_settings_tab(self, parent):
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(4, weight=1)
        ttk.Label(parent, text="Server 1 URL", style="Metric.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=8)
        ttk.Entry(parent, textvariable=self.server_one_var).grid(row=0, column=1, sticky="ew", pady=8)
        ttk.Label(parent, text="Server 2 URL", style="Metric.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=8)
        ttk.Entry(parent, textvariable=self.server_two_var).grid(row=1, column=1, sticky="ew", pady=8)

        ttk.Separator(parent).grid(row=2, column=0, columnspan=2, sticky="ew", pady=16)

        account_header = ttk.Frame(parent, style="Surface.TFrame")
        account_header.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        account_header.columnconfigure(0, weight=1)
        ttk.Label(account_header, text="Accounts", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.modern_button(account_header, "Add Account", self.add_account, "primary").grid(row=0, column=1, sticky="e")

        accounts_shell = ttk.Frame(parent, style="Surface.TFrame")
        accounts_shell.grid(row=4, column=0, columnspan=2, sticky="nsew")
        accounts_shell.columnconfigure(0, weight=1)
        accounts_shell.rowconfigure(0, weight=1)
        self.accounts_canvas = tk.Canvas(accounts_shell, bg=COLOR_SURFACE, highlightthickness=0, borderwidth=0)
        accounts_scroll = ttk.Scrollbar(accounts_shell, orient="vertical", command=self.accounts_canvas.yview)
        self.accounts_canvas.configure(yscrollcommand=accounts_scroll.set)
        self.accounts_canvas.grid(row=0, column=0, sticky="nsew")
        accounts_scroll.grid(row=0, column=1, sticky="ns")

        self.accounts_frame = ttk.Frame(self.accounts_canvas, style="Surface.TFrame")
        self.accounts_canvas_window = self.accounts_canvas.create_window((0, 0), window=self.accounts_frame, anchor="nw")
        self.accounts_frame.columnconfigure(0, weight=1)
        self.accounts_frame.bind("<Configure>", self._accounts_frame_configured)
        self.accounts_canvas.bind("<Configure>", self._accounts_canvas_configured)
        self.accounts_canvas.bind_all("<MouseWheel>", self._accounts_mousewheel)

        self.modern_button(parent, "Save Settings", self._save_settings, "primary").grid(row=5, column=0, sticky="w", pady=(16, 0))

    def _accounts_frame_configured(self, _event=None):
        if hasattr(self, "accounts_canvas"):
            self.accounts_canvas.configure(scrollregion=self.accounts_canvas.bbox("all"))

    def _accounts_canvas_configured(self, event):
        self.accounts_canvas.itemconfigure(self.accounts_canvas_window, width=event.width)

    def _accounts_mousewheel(self, event):
        if hasattr(self, "accounts_canvas") and self.accounts_canvas.winfo_ismapped():
            self.accounts_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def add_account(self, username="", password="", enabled=True, placement=None, session_cookie=""):
        row = {
            "frame": ttk.Frame(self.accounts_frame, padding=14, style="Card.TFrame"),
            "title": tk.StringVar(value=f"Account {len(self.account_rows) + 1}"),
            "enabled": tk.BooleanVar(value=enabled),
            "username": tk.StringVar(value=username),
            "password": tk.StringVar(value=password),
            "session_cookie": tk.StringVar(value=session_cookie),
            "session_status": tk.StringVar(),
            "placement": placement,
            "placement_text": tk.StringVar(value=self.format_placement(placement)),
            "runtime_hwnd": None,
            "runtime_pid": None,
        }
        frame = row["frame"]
        frame.grid(row=len(self.account_rows), column=0, sticky="ew", pady=(0, 10))
        frame.columnconfigure(2, weight=1)
        frame.columnconfigure(4, weight=1)

        ttk.Label(frame, textvariable=row["title"], style="CardTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        session_label = tk.Label(
            frame,
            textvariable=row["session_status"],
            bg=COLOR_CARD,
            font=("Segoe UI Semibold", 10),
        )
        session_label.grid(row=0, column=2, columnspan=3, sticky="e", padx=(0, 12), pady=(0, 10))
        self.modern_toggle(frame, "On", row["enabled"]).grid(row=0, column=5, sticky="e", pady=(0, 10))
        ttk.Label(frame, text="Username", style="CardMuted.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(frame, textvariable=row["username"]).grid(row=1, column=1, columnspan=2, sticky="ew", padx=(0, 12))
        ttk.Label(frame, text="Password", style="CardMuted.TLabel").grid(row=1, column=3, sticky="w", padx=(0, 8))
        ttk.Entry(frame, textvariable=row["password"], show="*").grid(row=1, column=4, columnspan=2, sticky="ew")
        ttk.Label(frame, text="Session cookie", style="CardMuted.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(10, 0))
        ttk.Entry(frame, textvariable=row["session_cookie"], show="*").grid(row=2, column=1, columnspan=5, sticky="ew", pady=(10, 0))
        self.modern_button(frame, "Set Window", lambda account=row: self.start_window_pick(account), "secondary").grid(row=3, column=0, sticky="w", pady=(10, 0))
        self.modern_button(frame, "Capture Cookie", lambda account=row: self.capture_cookie_for_account(account), "primary").grid(row=3, column=1, sticky="w", padx=(10, 0), pady=(10, 0))
        self.modern_button(frame, "Test Session", lambda account=row: self.test_session_for_account(account), "secondary").grid(row=3, column=2, sticky="w", padx=(10, 0), pady=(10, 0))
        self.modern_button(frame, "Remove", lambda account=row: self.remove_account(account), "secondary").grid(row=3, column=5, sticky="e", pady=(10, 0))
        ttk.Label(frame, textvariable=row["placement_text"], style="CardMuted.TLabel").grid(row=4, column=0, columnspan=6, sticky="w", pady=(10, 0))

        def refresh_session_status(*_args):
            has_cookie = bool(normalize_roblox_cookie(row["session_cookie"].get()))
            row["session_status"].set("Session saved" if has_cookie else "Cookie needed")
            session_label.configure(fg=COLOR_SUCCESS if has_cookie else COLOR_WARNING)

        row["session_cookie"].trace_add("write", refresh_session_status)
        row["session_cookie"].trace_add("write", lambda *_args: self._refresh_readiness())
        row["username"].trace_add("write", lambda *_args: self._refresh_readiness())
        row["password"].trace_add("write", lambda *_args: self._refresh_readiness())
        row["enabled"].trace_add("write", lambda *_args: self._refresh_readiness())
        refresh_session_status()

        self.account_rows.append(row)
        self._renumber_accounts()
        self._refresh_readiness()

    def format_placement(self, placement):
        if not placement:
            return "Window: not set"
        return f"Window: {placement['x']}, {placement['y']}  {placement['width']}x{placement['height']}"

    def start_window_pick(self, account):
        left, top, width, height = virtual_screen_geometry()
        overlay = tk.Toplevel(self)
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.attributes("-alpha", 0.18)
        overlay.configure(bg="#1d4ed8", cursor="crosshair")
        overlay.geometry(f"{width}x{height}{left:+d}{top:+d}")

        label = tk.Label(
            overlay,
            text="Click the Roblox window for this account",
            bg="#1d4ed8",
            fg="white",
            font=("Segoe UI", 22, "bold"),
        )
        label.place(relx=0.5, rely=0.5, anchor="center")
        self.status_var.set("Click the Roblox window to save this account's placement.")

        def choose(event):
            x, y = event.x_root, event.y_root
            overlay.withdraw()
            self.update()
            time.sleep(0.15)
            window = roblox_window_from_point(x, y)
            overlay.destroy()
            if not window:
                self.status_var.set("No Roblox window found under that click.")
                messagebox.showinfo("Window not found", "Click inside an open Roblox window.")
                return
            account["placement"] = window["placement"]
            account["runtime_hwnd"] = window["hwnd"]
            account["runtime_pid"] = window["pid"]
            account["placement_text"].set(self.format_placement(window["placement"]))
            self._save_settings()
            self._refresh_readiness()
            self.status_var.set("Saved Roblox window placement for this account.")

        def cancel(_event=None):
            overlay.destroy()
            self.status_var.set("Window selection cancelled.")

        overlay.bind("<Button-1>", choose)
        overlay.bind("<Escape>", cancel)
        overlay.focus_force()

    def capture_cookie_for_account(self, account):
        username = account["username"].get().strip() or "account"
        target_url = self.server_url(int(self.current_server_var.get() or 1)) or "https://www.roblox.com/"
        self.status_var.set(f"Opening Roblox login window for {username}.")
        threading.Thread(target=self._capture_cookie_worker, args=(account, username, target_url), daemon=True).start()

    def _capture_cookie_worker(self, account, username, target_url):
        browsers = automated_browser_candidates()
        if not browsers:
            self.after(0, lambda: self.status_var.set("Chrome or Edge was not found."))
            return

        port = free_local_port()
        profile_dir = Path(tempfile.mkdtemp(prefix="server-cookie-profile-"))
        process = subprocess.Popen(
            [
                str(browsers[0]),
                f"--remote-debugging-port={port}",
                f"--user-data-dir={profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-sync",
                "--new-window",
                roblox_login_url(target_url),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=hidden_process_flags(),
        )

        connection = None
        try:
            target = wait_for_debug_target(port, timeout=30)
            connection = DevToolsConnection(target["webSocketDebuggerUrl"], timeout=10)
            connection.call("Network.enable")
            deadline = time.time() + 300
            while time.time() < deadline:
                try:
                    cookies = connection.call("Network.getCookies", {"urls": ["https://www.roblox.com/"]}).get("cookies", [])
                    session = next((cookie for cookie in cookies if cookie.get("name") == ".ROBLOSECURITY" and cookie.get("value")), None)
                    if session:
                        value = session["value"]
                        self.after(0, lambda value=value: self._save_captured_cookie(account, value))
                        return
                except Exception:
                    pass
                time.sleep(2)
            self.after(0, lambda: self.status_var.set(f"Cookie capture timed out for {username}."))
        except Exception as exc:
            self.after(0, lambda err=str(exc): self.status_var.set(f"Cookie capture failed: {err}"))
        finally:
            if connection:
                connection.close()
            try:
                process.terminate()
            except Exception:
                pass

            def cleanup():
                try:
                    process.wait(timeout=8)
                except Exception:
                    try:
                        process.kill()
                    except Exception:
                        pass
                shutil.rmtree(profile_dir, ignore_errors=True)

            threading.Thread(target=cleanup, daemon=True).start()

    def _save_captured_cookie(self, account, value):
        account["session_cookie"].set(normalize_roblox_cookie(value))
        self._save_settings()
        self._refresh_readiness()
        self.status_var.set("Captured and saved Roblox session cookie.")

    def test_session_for_account(self, account):
        username = account["username"].get().strip() or "account"
        session_cookie = account["session_cookie"].get().strip()
        target_url = self.server_url(int(self.current_server_var.get() or 1))
        self.status_var.set(f"Testing saved Roblox session for {username}...")
        threading.Thread(
            target=self._test_session_worker,
            args=(username, session_cookie, target_url),
            daemon=True,
        ).start()

    def _test_session_worker(self, username, session_cookie, target_url):
        try:
            result = validate_roblox_session_cookie(session_cookie, target_url)
            name = result.get("username") or username
            self.after(0, lambda: self.status_var.set(f"Session OK for {name}."))
        except Exception as exc:
            self.after(0, lambda err=str(exc), name=username: self.status_var.set(f"Session test failed for {name}: {err}"))

    def remove_account(self, account):
        if len(self.account_rows) <= 1:
            account["username"].set("")
            account["password"].set("")
            account["session_cookie"].set("")
            account["enabled"].set(True)
            self._refresh_readiness()
            return
        account["frame"].destroy()
        self.account_rows.remove(account)
        self._renumber_accounts()
        self._refresh_readiness()

    def _renumber_accounts(self):
        for index, account in enumerate(self.account_rows, start=1):
            account["title"].set(f"Account {index}")
            account["frame"].grid(row=index - 1, column=0, sticky="ew", pady=(0, 10))

    def account_settings(self):
        accounts = []
        for account in self.account_rows:
            accounts.append(
                {
                    "username": account["username"].get().strip(),
                    "password": account["password"].get(),
                    "session_cookie": account["session_cookie"].get().strip(),
                    "enabled": bool(account["enabled"].get()),
                    "placement": account.get("placement"),
                }
            )
        return accounts

    def enabled_account_entries(self):
        entries = []
        for account in self.account_rows:
            if not account["enabled"].get():
                continue
            entries.append(
                {
                    "row": account,
                    "username": account["username"].get().strip(),
                    "password": account["password"].get(),
                    "session_cookie": account["session_cookie"].get().strip(),
                    "placement": account.get("placement"),
                }
            )
        return entries

    def _load_settings(self):
        if not SETTINGS_FILE.exists():
            self.add_account()
            self._sync_current_server_text()
            return
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            self.add_account()
            self._sync_current_server_text()
            return

        self.server_one_var.set(data.get("server_one", data.get("site_one", "")))
        self.server_two_var.set(data.get("server_two", data.get("site_two", "")))
        accounts = data.get("accounts")
        if not accounts:
            accounts = [
                {
                    "username": data.get("username", ""),
                    "password_protected": data.get("password_protected", ""),
                    "enabled": True,
                }
            ]

        for account in accounts:
            self.add_account(
                username=account.get("username", ""),
                password=unprotect_text(account.get("password_protected", "")),
                enabled=bool(account.get("enabled", True)),
                placement=account.get("placement"),
                session_cookie=unprotect_text(account.get("session_cookie_protected", "")),
            )

        if not self.account_rows:
            self.add_account()
        self.current_server_var.set(int(data.get("current_server", 1) or 1))
        self.auto_rotate_var.set(bool(data.get("auto_rotate", True)))
        self.keep_alive_var.set(bool(data.get("keep_alive", False)))
        try:
            keep_alive_minutes = max(1, min(120, int(data.get("keep_alive_minutes", DEFAULT_KEEP_ALIVE_MINUTES) or DEFAULT_KEEP_ALIVE_MINUTES)))
        except Exception:
            keep_alive_minutes = DEFAULT_KEEP_ALIVE_MINUTES
        self.keep_alive_minutes_var.set(keep_alive_minutes)
        try:
            self.detector_popup_sensitivity_var.set(max(0, min(100, int(data.get("detector_popup_sensitivity", DEFAULT_POPUP_SENSITIVITY)))))
        except Exception:
            self.detector_popup_sensitivity_var.set(DEFAULT_POPUP_SENSITIVITY)
        try:
            self.detector_activity_sensitivity_var.set(max(0, min(100, int(data.get("detector_activity_sensitivity", DEFAULT_ACTIVITY_SENSITIVITY)))))
        except Exception:
            self.detector_activity_sensitivity_var.set(DEFAULT_ACTIVITY_SENSITIVITY)
        try:
            self.detector_sample_count_var.set(max(2, min(6, int(data.get("detector_sample_count", DEFAULT_DETECTOR_SAMPLE_COUNT)))))
        except Exception:
            self.detector_sample_count_var.set(DEFAULT_DETECTOR_SAMPLE_COUNT)
        try:
            self.detector_sample_delay_var.set(max(0.5, min(3.0, float(data.get("detector_sample_delay", DEFAULT_DETECTOR_SAMPLE_DELAY)))))
        except Exception:
            self.detector_sample_delay_var.set(DEFAULT_DETECTOR_SAMPLE_DELAY)
        switch_time = str(data.get("switch_time", "07:00"))
        try:
            hour_text, minute_text = switch_time.split(":", 1)
            self._set_switch_time_values(max(0, min(23, int(hour_text))), max(0, min(59, int(minute_text))))
        except Exception:
            self._set_switch_time_values(7, 0)
        self._sync_current_server_text()
        self._refresh_readiness()

    def _save_settings(self):
        self._refresh_schedule()
        hour, minute = self.switch_time_values()
        self._set_switch_time_values(hour, minute)
        try:
            keep_alive_minutes = max(1, min(120, int(self.keep_alive_minutes_var.get())))
        except Exception:
            keep_alive_minutes = DEFAULT_KEEP_ALIVE_MINUTES
        self.keep_alive_minutes_var.set(keep_alive_minutes)
        data = {
            "server_one": self.server_one_var.get().strip(),
            "server_two": self.server_two_var.get().strip(),
            "accounts": [
                {
                    "username": account["username"],
                    "password_protected": protect_text(account["password"]),
                    "session_cookie_protected": protect_text(normalize_roblox_cookie(account["session_cookie"])),
                    "enabled": account["enabled"],
                    "placement": account["placement"],
                }
                for account in self.account_settings()
            ],
            "current_server": int(self.current_server_var.get()),
            "switch_time": f"{hour:02d}:{minute:02d}",
            "auto_rotate": bool(self.auto_rotate_var.get()),
            "keep_alive": bool(self.keep_alive_var.get()),
            "keep_alive_minutes": keep_alive_minutes,
            "detector_popup_sensitivity": int(self.detector_popup_sensitivity_var.get()),
            "detector_activity_sensitivity": int(self.detector_activity_sensitivity_var.get()),
            "detector_sample_count": int(self.detector_sample_count_var.get()),
            "detector_sample_delay": float(self.detector_sample_delay_var.get()),
        }
        SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self._refresh_readiness()
        self.status_var.set("Settings saved.")

    def switch_time_values(self):
        try:
            hour = max(0, min(23, int(str(self.switch_hour_var.get()).strip())))
            minute = max(0, min(59, int(str(self.switch_minute_var.get()).strip())))
        except Exception:
            hour, minute = 7, 0
        return hour, minute

    def _set_switch_time_values(self, hour, minute):
        self.switch_hour_var.set(f"{int(hour):02d}")
        self.switch_minute_var.set(f"{int(minute):02d}")

    def _refresh_schedule(self):
        hour, minute = self.switch_time_values()
        self.next_switch = next_switch_time(hour, minute)
        self._update_countdown()

    def set_switch_time(self):
        hour, minute = self.switch_time_values()
        self._set_switch_time_values(hour, minute)
        self._refresh_schedule()
        self._save_settings()
        self.status_var.set(f"Next switch time set to {hour:02d}:{minute:02d}.")

    def _update_countdown(self):
        if not self.auto_rotate_var.get():
            self.countdown_var.set("Next switch: auto switch is off")
            return
        if not self.next_switch:
            self._refresh_schedule()
            return
        remaining = self.next_switch - dt.datetime.now()
        self.countdown_var.set(
            f"Next switch: {self.next_switch.strftime('%Y-%m-%d %I:%M %p')} ({format_timedelta(remaining)})"
        )

    def keep_alive_interval_ms(self):
        try:
            minutes = max(1, min(120, int(self.keep_alive_minutes_var.get())))
        except Exception:
            minutes = DEFAULT_KEEP_ALIVE_MINUTES
        return minutes * 60 * 1000

    def keep_alive_toggled(self):
        self._save_settings()
        self._schedule_keep_alive_tick()
        state = "on" if self.keep_alive_var.get() else "off"
        self.status_var.set(f"Keep alive turned {state}.")

    def reset_keep_alive_timer(self):
        self._save_settings()
        self._schedule_keep_alive_tick()
        minutes = self.keep_alive_interval_ms() // 60000
        if self.keep_alive_var.get():
            self.status_var.set(f"Keep alive timer reset to {minutes} minute(s).")
        else:
            self.status_var.set("Keep alive is off. Turn it on to start the timer.")

    def _schedule_keep_alive_tick(self):
        if self.keep_alive_after_id:
            try:
                self.after_cancel(self.keep_alive_after_id)
            except Exception:
                pass
            self.keep_alive_after_id = None
        if not self.keep_alive_var.get():
            self.next_keep_alive = None
            self._update_keep_alive_countdown()
            return
        interval_ms = self.keep_alive_interval_ms()
        self.next_keep_alive = dt.datetime.now() + dt.timedelta(milliseconds=interval_ms)
        self.keep_alive_after_id = self.after(interval_ms, self._keep_alive_tick)
        self._update_keep_alive_countdown()

    def _update_keep_alive_countdown(self):
        if not self.keep_alive_var.get():
            self.keep_alive_countdown_var.set("Keep alive: off")
            return
        if self.keep_alive_in_progress:
            self.keep_alive_countdown_var.set("Keep alive: running")
            return
        if not self.next_keep_alive:
            self.keep_alive_countdown_var.set("Keep alive: --")
            return
        remaining = self.next_keep_alive - dt.datetime.now()
        self.keep_alive_countdown_var.set(f"Keep alive: {format_timedelta(remaining)}")

    def _sync_current_server_text(self):
        server = int(self.current_server_var.get() or 1)
        self.active_server_var.set(f"Current server: Server {server}")

    def server_url(self, number):
        return normalize_url(self.server_one_var.get() if number == 1 else self.server_two_var.get())

    def _refresh_readiness(self):
        if not hasattr(self, "readiness_var"):
            return
        enabled_accounts = self.enabled_account_entries()
        missing = []
        if not self.server_url(1):
            missing.append("Server 1 URL")
        if not self.server_url(2):
            missing.append("Server 2 URL")
        if not enabled_accounts:
            missing.append("enabled account")

        missing_cookies = [account["username"] or "unnamed account" for account in enabled_accounts if not account.get("session_cookie")]
        missing_placements = [account["username"] or "unnamed account" for account in enabled_accounts if not account.get("placement")]

        if missing:
            text = "Setup needed: " + ", ".join(missing) + "."
            bg, fg = "#fef2f2", COLOR_DANGER_DARK
        elif missing_cookies:
            shown = ", ".join(missing_cookies[:3])
            extra = "" if len(missing_cookies) <= 3 else f" and {len(missing_cookies) - 3} more"
            text = f"Action needed: capture Roblox session cookies for {shown}{extra} before launching."
            bg, fg = "#fff7ed", COLOR_WARNING
        else:
            if missing_placements:
                shown = ", ".join(missing_placements[:3])
                extra = "" if len(missing_placements) <= 3 else f" and {len(missing_placements) - 3} more"
                text = f"Launch ready. Keep-alive window placement still needed for {shown}{extra}."
                bg, fg = "#eff6ff", COLOR_PRIMARY_DARK
            else:
                text = f"Ready to launch {len(enabled_accounts)} enabled account(s)."
                bg, fg = "#ecfdf5", COLOR_SUCCESS

        self.readiness_var.set(text)
        if self.readiness_label:
            parent = self.readiness_label.master
            parent.configure(bg=bg, highlightbackground=fg)
            for child in parent.winfo_children():
                try:
                    child.configure(bg=bg)
                except Exception:
                    pass
            self.readiness_label.configure(fg=fg)

    def validate_launch_inputs(self, server_number):
        url = self.server_url(server_number)
        enabled_accounts = self.enabled_account_entries()
        if not url:
            messagebox.showinfo("Server needed", f"Enter the Server {server_number} address in Settings.")
            return None
        if not enabled_accounts:
            messagebox.showinfo("Account needed", "Turn on at least one Roblox account in Settings.")
            return None
        for index, account in enumerate(enabled_accounts, start=1):
            if not account["username"]:
                messagebox.showinfo("Login needed", f"Account {index} is on but is missing a username.")
                return None
            if not account["password"] and not account["session_cookie"]:
                messagebox.showinfo("Login needed", f"Account {index} needs a password or session cookie.")
                return None
        return url, enabled_accounts

    def password_only_accounts(self, accounts):
        return [account for account in accounts if account.get("password") and not account.get("session_cookie")]

    def launch_server(self, server_number, automatic=False):
        if self.launch_in_progress:
            self.status_var.set("A server launch is already in progress.")
            return
        details = self.validate_launch_inputs(server_number)
        if not details:
            return
        url, accounts = details
        password_only = self.password_only_accounts(accounts)
        if password_only:
            names = ", ".join(account["username"] or "unnamed account" for account in password_only)
            message = (
                "Roblox is blocking the hidden password-login path on this machine. "
                f"Capture Cookie for: {names}."
            )
            self.status_var.set(message)
            if not automatic:
                messagebox.showwarning(
                    "Capture Cookie Needed",
                    message + "\n\nOpen Settings, click Capture Cookie for each enabled account, then try Launch again.",
                )
            return
        self._save_settings()
        self.launch_in_progress = True
        reason = "automatic switch" if automatic else "manual launch"
        if len(accounts) == 1:
            self.status_var.set(f"Starting Server {server_number} in the background ({reason})...")
        else:
            self.status_var.set(
                f"Starting Server {server_number} for {len(accounts)} accounts ({reason})..."
            )

        def worker():
            try:
                if len(accounts) == 1:
                    self.multi_instance_lock.release()
                    account = accounts[0]
                    result = self.launch_account_entry(url, account, stop_existing=True)
                else:
                    result = self.launch_multiple_accounts(url, accounts, server_number)
                self.after(0, lambda: self._launch_complete(server_number, result, None))
            except Exception as exc:
                self.after(0, lambda: self._launch_complete(server_number, None, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def launch_account_entry(self, url, account, stop_existing, window_timeout=30):
        existing_hwnds = [window["hwnd"] for window in enum_roblox_windows()]
        result = launch_server_background(
            url,
            account["username"],
            account["password"],
            session_cookie=account.get("session_cookie", ""),
            stop_existing=stop_existing,
            wait_for_player=False,
        )
        window = wait_for_new_roblox_window(existing_hwnds, timeout=window_timeout)
        if window:
            placement = account.get("placement")
            if placement:
                move_window_to_placement(window["hwnd"], placement)
                time.sleep(0.4)
                updated = get_window_rect(window["hwnd"])
                if updated:
                    window["placement"] = updated
            account["row"]["runtime_hwnd"] = window["hwnd"]
            account["row"]["runtime_pid"] = window["pid"]
            result["window_detected"] = True
        else:
            result["window_detected"] = False
            if result.get("status") == "launch_requested":
                result["status"] = "launch_requested_no_window"
        return result

    def launch_multiple_accounts(self, url, accounts, server_number):
        stop_roblox()
        time.sleep(2)
        self.multi_instance_lock.acquire()

        results = []
        for index, account in enumerate(accounts, start=1):
            self.after(
                0,
                lambda idx=index, total=len(accounts), name=account["username"]: self.status_var.set(
                    f"Launching Server {server_number}: account {idx} of {total} ({name})..."
                ),
            )
            result = self.launch_account_entry(url, account, stop_existing=False)
            results.append(result)
            if index < len(accounts):
                time.sleep(4)

        return {
            "status": "roblox_started",
            "accounts_launched": len(results),
            "windows_detected": sum(1 for result in results if result.get("window_detected")),
            "results": results,
        }

    def account_window(self, account):
        hwnd = account["row"].get("runtime_hwnd")
        if hwnd and is_window(hwnd):
            placement = get_window_rect(hwnd)
            if placement:
                return {"hwnd": hwnd, "pid": account["row"].get("runtime_pid"), "placement": placement}

        window = find_window_by_placement(account.get("placement"))
        if window:
            account["row"]["runtime_hwnd"] = window["hwnd"]
            account["row"]["runtime_pid"] = window["pid"]
        return window

    def reconnect_account(self, account, url, enabled_count):
        if not url:
            return

        if enabled_count > 1:
            self.multi_instance_lock.acquire()

        window = self.account_window(account)
        if window and window.get("pid"):
            kill_process(window["pid"])
            time.sleep(2)

        self.launch_account_entry(url, account, stop_existing=False)

    def accounts_ready_for_keep_alive(self):
        return [account for account in self.enabled_account_entries() if account.get("placement")]

    def detector_settings(self):
        try:
            popup_sensitivity = max(0, min(100, int(self.detector_popup_sensitivity_var.get())))
        except Exception:
            popup_sensitivity = DEFAULT_POPUP_SENSITIVITY
        try:
            activity_sensitivity = max(0, min(100, int(self.detector_activity_sensitivity_var.get())))
        except Exception:
            activity_sensitivity = DEFAULT_ACTIVITY_SENSITIVITY
        try:
            sample_count = max(2, min(6, int(self.detector_sample_count_var.get())))
        except Exception:
            sample_count = DEFAULT_DETECTOR_SAMPLE_COUNT
        try:
            sample_delay = max(0.5, min(3.0, float(self.detector_sample_delay_var.get())))
        except Exception:
            sample_delay = DEFAULT_DETECTOR_SAMPLE_DELAY

        return {
            "sample_count": sample_count,
            "sample_delay": sample_delay,
            "dark_ratio_limit": 0.68 - (popup_sensitivity * 0.002),
            "mean_limit": 85 + (popup_sensitivity * 0.4),
            "min_motion_score": 0.65 - (activity_sensitivity * 0.006),
        }

    def _detector_setting_changed(self, save=False):
        if save:
            self._save_settings()
            self.status_var.set("Disconnect sensor settings saved.")

    def reposition_windows(self):
        accounts = self.accounts_ready_for_keep_alive()
        if not accounts:
            self.status_var.set("No enabled accounts have saved Roblox window placements yet.")
            return
        self.status_var.set(f"Repositioning {len(accounts)} Roblox window(s)...")
        threading.Thread(target=self._reposition_windows_worker, args=(accounts,), daemon=True).start()

    def _reposition_windows_worker(self, accounts):
        moved = 0
        missing = []
        for account in accounts:
            window = self.account_window(account)
            if not window:
                missing.append(account["username"])
                continue
            if move_window_to_placement(window["hwnd"], account["placement"]):
                moved += 1
            time.sleep(0.2)
        if missing:
            detail = ", ".join(missing)
            self.after(0, lambda: self.status_var.set(f"Repositioned {moved}; missing windows: {detail}."))
        else:
            self.after(0, lambda: self.status_var.set(f"Repositioned {moved} Roblox window(s)."))

    def test_keep_alive_keys(self):
        accounts = self.accounts_ready_for_keep_alive()
        if not accounts:
            self.status_var.set("No enabled accounts have saved Roblox windows yet.")
            return
        self.status_var.set(f"Testing click + Tab, Tab, C, C for {len(accounts)} account(s)...")
        threading.Thread(target=self._test_keep_alive_keys_worker, args=(accounts,), daemon=True).start()

    def _test_keep_alive_keys_worker(self, accounts):
        sent = 0
        missing = []
        for account in accounts:
            window = self.account_window(account)
            if not window:
                missing.append(account["username"])
                continue
            send_keep_alive_keys(window["hwnd"])
            sent += 1
            time.sleep(0.5)

        if missing:
            detail = ", ".join(missing)
            self.after(0, lambda: self.status_var.set(f"Sent click + Tab, Tab, C, C to {sent}; missing windows: {detail}."))
        else:
            self.after(0, lambda: self.status_var.set(f"Sent click + Tab, Tab, C, C to {sent} account(s)."))

    def test_alive_check(self):
        accounts = self.accounts_ready_for_keep_alive()
        if not accounts:
            self.status_var.set("No enabled accounts have saved Roblox windows yet.")
            return
        self.status_var.set(f"Testing alive check for {len(accounts)} account(s)...")
        threading.Thread(target=self._test_alive_check_worker, args=(accounts,), daemon=True).start()

    def _test_alive_check_worker(self, accounts):
        results = []
        detector = self.detector_settings()
        for account in accounts:
            window = self.account_window(account)
            if not window:
                results.append(f"{account['username']}: no window")
                continue
            health = roblox_window_health(window["placement"], hwnd=window["hwnd"], **detector)
            label = "active" if health["healthy"] else "disconnected"
            rect = health.get("capture_rect") or window.get("placement") or {}
            results.append(
                f"{account['username']}: {label} ({health['reason']}, motion {health.get('motion', 0):.2f}, tab {health.get('tab_response', 0):.2f}, capture {rect.get('x', '?')},{rect.get('y', '?')} {rect.get('width', '?')}x{rect.get('height', '?')})"
            )
        text = " | ".join(results)
        self.after(0, lambda: self.status_var.set(text))

    def diagnostics_snapshot(self):
        accounts = []
        for index, account in enumerate(self.account_rows, start=1):
            accounts.append(
                {
                    "index": index,
                    "username": account["username"].get().strip(),
                    "has_password": bool(account["password"].get()),
                    "session_cookie": account["session_cookie"].get().strip(),
                    "enabled": bool(account["enabled"].get()),
                    "placement": account.get("placement"),
                }
            )
        return {
            "server_one": self.server_url(1),
            "server_two": self.server_url(2),
            "current_server": int(self.current_server_var.get() or 1),
            "current_url": self.server_url(int(self.current_server_var.get() or 1)),
            "auto_rotate": bool(self.auto_rotate_var.get()),
            "keep_alive": bool(self.keep_alive_var.get()),
            "keep_alive_minutes": self.keep_alive_interval_ms() // 60000,
            "detector": {
                "sample_count": int(self.detector_sample_count_var.get()),
                "sample_delay": float(self.detector_sample_delay_var.get()),
            },
            "accounts": accounts,
        }

    def run_diagnostics(self):
        if self.launch_in_progress:
            self.status_var.set("A launch is already running. Try diagnostics again after it finishes.")
            return
        snapshot = self.diagnostics_snapshot()
        self.status_var.set("Running launcher diagnostics...")
        threading.Thread(target=self._diagnostics_worker, args=(snapshot,), daemon=True).start()

    def _diagnostics_worker(self, snapshot):
        report, issue_count, warning_count = build_diagnostics_report(snapshot)
        self.after(0, lambda: self._show_diagnostics_report(report, issue_count, warning_count))

    def _show_diagnostics_report(self, report, issue_count, warning_count):
        if issue_count:
            summary = f"Diagnostics found {issue_count} issue(s) and {warning_count} warning(s)."
        elif warning_count:
            summary = f"Diagnostics passed with {warning_count} warning(s)."
        else:
            summary = "Diagnostics passed. Launcher setup looks ready."
        self.status_var.set(summary)
        messagebox.showinfo("Launcher Diagnostics", report)

    def _keep_alive_tick(self):
        self.keep_alive_after_id = None
        try:
            if self.keep_alive_var.get() and not self.launch_in_progress and not self.keep_alive_in_progress:
                enabled_accounts = self.enabled_account_entries()
                accounts = [account for account in enabled_accounts if account.get("placement")]
                if accounts:
                    self.keep_alive_in_progress = True
                    current_url = self.server_url(int(self.current_server_var.get() or 1))
                    threading.Thread(
                        target=self._run_keep_alive_cycle,
                        args=(accounts, current_url, len(enabled_accounts)),
                        daemon=True,
                    ).start()
        finally:
            self._schedule_keep_alive_tick()

    def _run_keep_alive_cycle(self, accounts, current_url, enabled_count):
        try:
            detector = self.detector_settings()
            for account in accounts:
                try:
                    window = self.account_window(account)
                    if not window:
                        self.after(0, lambda name=account["username"]: self.status_var.set(f"No saved Roblox window found for {name}; reconnecting."))
                        self.reconnect_account(account, current_url, enabled_count)
                        continue

                    health = roblox_window_health(window["placement"], hwnd=window["hwnd"], **detector)
                    if not health["healthy"]:
                        self.after(
                            0,
                            lambda name=account["username"], reason=health["reason"]: self.status_var.set(
                                f"Roblox looks disconnected for {name} ({reason}); reconnecting."
                            ),
                        )
                        self.reconnect_account(account, current_url, enabled_count)
                        continue

                    send_keep_alive_keys(window["hwnd"])
                    self.after(0, lambda name=account["username"]: self.status_var.set(f"Keep alive sent to {name}."))
                    time.sleep(0.8)
                except Exception as exc:
                    self.after(0, lambda err=str(exc): self.status_var.set(f"Keep alive check failed: {err}"))
        finally:
            self.keep_alive_in_progress = False

    def _launch_complete(self, server_number, result, error):
        self.launch_in_progress = False
        if error:
            self.status_var.set(f"Server {server_number} launch failed: {error}")
            return
        self.current_server_var.set(server_number)
        self._sync_current_server_text()
        self._save_settings()
        status = result.get("status") if result else "unknown"
        account_count = result.get("accounts_launched") if result else None
        if account_count:
            detected = result.get("windows_detected", account_count)
            self.status_var.set(f"Server {server_number} launch requested for {account_count} accounts ({detected} windows detected).")
        elif status == "roblox_started":
            self.status_var.set(f"Server {server_number} launched. Background browser closed.")
        elif status == "launch_requested":
            self.status_var.set(f"Server {server_number} launch requested. Waiting can continue in Roblox.")
        elif status == "launch_requested_no_window":
            self.status_var.set(f"Server {server_number} launch requested, but no new Roblox window was detected yet.")
        elif status == "player_start_requested":
            self.status_var.set(
                f"Server {server_number} login finished and Roblox Player was requested."
            )
        else:
            self.status_var.set(f"Server {server_number} launch finished with status: {status}.")

    def switch_now(self):
        next_server = 2 if int(self.current_server_var.get() or 1) == 1 else 1
        self.launch_server(next_server)

    def stop_roblox_from_ui(self):
        stop_roblox()
        self.multi_instance_lock.release()
        self.status_var.set("Stopped Roblox.")

    def _tick(self):
        self._update_countdown()
        self._update_keep_alive_countdown()
        now = dt.datetime.now()
        if self.auto_rotate_var.get() and self.next_switch and now >= self.next_switch:
            switch_key = self.next_switch.strftime("%Y-%m-%d %H:%M")
            if self.last_switch_key != switch_key:
                self.last_switch_key = switch_key
                next_server = 2 if int(self.current_server_var.get() or 1) == 1 else 1
                self.status_var.set(f"Scheduled switch time reached. Moving to Server {next_server}.")
                self.launch_server(next_server, automatic=True)
            self._refresh_schedule()
        self.after(1000, self._tick)

    def _close(self):
        self._save_settings()
        if self.keep_alive_after_id:
            try:
                self.after_cancel(self.keep_alive_after_id)
            except Exception:
                pass
        self.multi_instance_lock.release()
        self.destroy()


def main():
    app = ServerLauncher()
    app.mainloop()


if __name__ == "__main__":
    main()
