#!/usr/bin/env python3
"""
AC's PyBoy GB Emulator 0.1.1

A single-file Game Boy / Game Boy Color frontend for Python 3.14+,
including native Apple Silicon Macs.
The emulator core is provided by PyBoy. The original blue interface is drawn
entirely in code with pygame-ce; there are no bundled images, fonts, ROMs, BIOS
files, or other GUI assets.

Only load ROM dumps that you are legally entitled to use.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback
from typing import Callable


APP_TITLE = "AC's PyBoy GB Emulator 0.1.1"
WINDOW_SIZE = (960, 640)
UI_FPS = 60
GAMEBOY_FPS = 60.0
GAMEBOY_FRAME_TIME = 1.0 / GAMEBOY_FPS
SUPPORTED_ROM_EXTENSIONS = {".gb", ".gbc"}
IS_MACOS = sys.platform == "darwin"


def _version_tuple(version: str) -> tuple[int, ...]:
    """Turn a package version into a tuple without requiring packaging."""
    numbers = re.findall(r"\d+", version)
    return tuple(int(number) for number in numbers[:3]) or (0,)


def _package_needs_install(distribution: str, minimum: str, module: str) -> bool:
    try:
        installed = importlib.metadata.version(distribution)
        if _version_tuple(installed) < _version_tuple(minimum):
            return True
    except importlib.metadata.PackageNotFoundError:
        return True

    # Probe each binary dependency in its own process. On macOS, importing
    # PyBoy and pygame here would load two private SDL2 frameworks into this
    # process before the app starts. Those frameworks both register the same
    # Objective-C SDLApplication class and can crash Tk/Cocoa on Apple Silicon.
    try:
        probe = subprocess.run(
            [sys.executable, "-c", f"import {module}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    return probe.returncode != 0


def _show_macos_alert(message: str) -> bool:
    """Show a Cocoa alert out of process, keeping Tk away from SDL on macOS."""
    if not IS_MACOS:
        return False
    script = """
on run argv
    display alert "AC's PyBoy GB Emulator" message (item 1 of argv) \
        as critical buttons {"OK"} default button "OK"
end run
"""
    try:
        result = subprocess.run(
            ["osascript", "-e", script, message],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _show_bootstrap_error(message: str) -> None:
    print(message, file=sys.stderr)
    if _show_macos_alert(message):
        return
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_TITLE, message, parent=root)
        root.destroy()
    except Exception:
        pass


def ensure_dependencies() -> None:
    """Install the current frontend dependencies into this Python interpreter."""
    requirements: list[str] = []
    if _package_needs_install("pyboy", "2.7.0", "pyboy"):
        requirements.append("pyboy>=2.7.0")

    # pygame-ce imports as ``pygame``. Probe it outside this process so its SDL
    # framework cannot collide with PyBoy's optional PySDL2 plugin at bootstrap.
    if _package_needs_install("pygame-ce", "2.5.7", "pygame"):
        requirements.append("pygame-ce>=2.5.7")

    if not requirements:
        return

    print(f"{APP_TITLE}: installing " + ", ".join(requirements) + " ...")
    base_command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--disable-pip-version-check",
        "--no-input",
        *requirements,
    ]

    try:
        import pip  # noqa: F401
    except ImportError:
        try:
            subprocess.run(
                [sys.executable, "-m", "ensurepip", "--upgrade"],
                check=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RuntimeError("pip is unavailable and could not be installed.") from exc

    attempts = [base_command]
    if sys.prefix == getattr(sys, "base_prefix", sys.prefix):
        attempts.append(base_command[:4] + ["--user"] + base_command[4:])

    last_error = ""
    for command in attempts:
        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if result.returncode == 0:
            importlib.invalidate_caches()
            return
        last_error = result.stdout.strip()

    tail = "\n".join(last_error.splitlines()[-18:])
    raise RuntimeError(
        "Automatic dependency installation failed.\n\n"
        f"Run this command with Python 3.14, then start the emulator again:\n"
        f"{sys.executable} -m pip install --upgrade pyboy pygame-ce\n\n"
        f"Installer output:\n{tail}"
    )


try:
    ensure_dependencies()
except Exception as bootstrap_error:
    _show_bootstrap_error(str(bootstrap_error))
    raise SystemExit(1) from bootstrap_error


os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

# PyBoy imports its optional PySDL2 window plugin even when ``window="null"``.
# This frontend already uses pygame-ce's SDL2. Preventing that unused optional
# import on macOS avoids loading two SDL2 frameworks with duplicate Cocoa
# classes. PyBoy's null renderer remains fully functional.
if IS_MACOS:
    sys.modules["sdl2"] = None
try:
    import pygame  # noqa: E402
    from pyboy import PyBoy  # noqa: E402
finally:
    if IS_MACOS and sys.modules.get("sdl2") is None:
        sys.modules.pop("sdl2", None)


# Blue-hue theme. Every visual is generated below; no asset files are needed.
INK = (2, 6, 14)
BACKGROUND = (4, 14, 32)
PANEL = (7, 28, 57)
PANEL_LIGHT = (10, 42, 78)
BLACK_BUTTON = (1, 4, 10)
BLACK_BUTTON_HOVER = (9, 20, 35)
BLUE = (0, 174, 239)
BRIGHT_BLUE = (103, 215, 255)
SOFT_BLUE = (53, 139, 190)
DIM_BLUE = (27, 83, 120)
OFF_WHITE = (211, 243, 255)
SUCCESS = (52, 224, 179)
WARNING = (255, 202, 80)
ERROR = (255, 95, 120)


def draw_text(
    surface: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    color: tuple[int, int, int],
    position: tuple[int, int],
    *,
    anchor: str = "topleft",
) -> pygame.Rect:
    image = font.render(text, True, color)
    rect = image.get_rect()
    setattr(rect, anchor, position)
    surface.blit(image, rect)
    return rect


def rounded_panel(
    surface: pygame.Surface,
    rect: pygame.Rect,
    fill: tuple[int, int, int],
    border: tuple[int, int, int] = DIM_BLUE,
    radius: int = 12,
) -> None:
    pygame.draw.rect(surface, fill, rect, border_radius=radius)
    pygame.draw.rect(surface, border, rect, width=1, border_radius=radius)


class ActionButton:
    def __init__(
        self,
        rect: pygame.Rect,
        label: str,
        action: Callable[[], None],
        *,
        enabled: Callable[[], bool] | None = None,
    ) -> None:
        self.rect = rect
        self.label = label
        self.action = action
        self.enabled = enabled or (lambda: True)

    def draw(
        self,
        surface: pygame.Surface,
        font: pygame.font.Font,
        mouse_position: tuple[int, int],
    ) -> None:
        active = self.enabled()
        hover = active and self.rect.collidepoint(mouse_position)
        fill = BLACK_BUTTON_HOVER if hover else BLACK_BUTTON
        border = BRIGHT_BLUE if hover else (BLUE if active else DIM_BLUE)
        text_color = BRIGHT_BLUE if active else DIM_BLUE
        pygame.draw.rect(surface, fill, self.rect, border_radius=8)
        pygame.draw.rect(surface, border, self.rect, width=2, border_radius=8)
        draw_text(
            surface,
            font,
            self.label,
            text_color,
            self.rect.center,
            anchor="center",
        )

    def click(self, position: tuple[int, int]) -> bool:
        if self.enabled() and self.rect.collidepoint(position):
            self.action()
            return True
        return False


class AudioOutput:
    """Small streaming bridge from PyBoy's per-frame PCM to pygame."""

    def __init__(self) -> None:
        self.available = pygame.mixer.get_init() is not None
        self.channel: pygame.mixer.Channel | None = None
        self.muted = False
        self.volume = 0.72
        if self.available:
            try:
                self.channel = pygame.mixer.Channel(0)
            except pygame.error:
                self.available = False

    def clear(self) -> None:
        if self.channel is not None:
            self.channel.stop()

    def toggle_mute(self) -> bool:
        self.muted = not self.muted
        if self.muted:
            self.clear()
        return self.muted

    def feed(self, samples: object) -> None:
        if not self.available or self.muted or self.channel is None:
            return
        try:
            raw = samples.tobytes()  # PyBoy exposes signed 8-bit stereo ndarray.
            if not raw:
                return
            sound = pygame.mixer.Sound(buffer=raw)
            sound.set_volume(self.volume)
            if not self.channel.get_busy():
                self.channel.play(sound)
            elif self.channel.get_queue() is None:
                self.channel.queue(sound)
            # When two buffers are already pending, dropping one is preferable
            # to letting audio latency grow without bounds.
        except (AttributeError, ValueError, pygame.error):
            self.available = False


class EmulatorApp:
    def __init__(self, initial_rom: str | None = None) -> None:
        pygame.mixer.pre_init(frequency=48_000, size=-8, channels=2, buffer=512)
        pygame.init()
        pygame.display.set_caption(APP_TITLE)
        self.window = pygame.display.set_mode(WINDOW_SIZE)
        self.clock = pygame.time.Clock()

        self.font_small = pygame.font.Font(None, 20)
        self.font_body = pygame.font.Font(None, 23)
        self.font_button = pygame.font.Font(None, 22)
        self.font_heading = pygame.font.Font(None, 32)
        self.font_title = pygame.font.Font(None, 42)

        self.pyboy: PyBoy | None = None
        self.rom_path: Path | None = None
        self.rom_name = "NO CARTRIDGE"
        self.game_title = "WAITING FOR ROM"
        self.paused = False
        self.running = True
        self.show_about = False
        self.quick_state: io.BytesIO | None = None
        self.status_text = "LOAD OR DROP A LEGAL .GB / .GBC ROM"
        self.status_color = SOFT_BLUE
        self.status_until = 0.0
        self.accumulator = 0.0
        self.fps = 0.0
        self.frame_surface: pygame.Surface | None = None
        self.audio = AudioOutput()
        self.held_inputs: set[str] = set()
        self.pointer_input: str | None = None

        self.screen_rect = pygame.Rect(48, 112, 480, 432)
        self.control_panel = pygame.Rect(552, 96, 360, 464)
        self.action_buttons = self._build_action_buttons()
        self.controller_regions = self._build_controller_regions()

        if initial_rom:
            self.load_rom(initial_rom)

    @property
    def has_rom(self) -> bool:
        return self.pyboy is not None

    def _build_action_buttons(self) -> list[ActionButton]:
        x, y = 570, 112
        width, height, gap = 101, 38, 8
        enabled = lambda: self.has_rom
        return [
            ActionButton(pygame.Rect(x, y, width, height), "LOAD ROM", self.choose_rom),
            ActionButton(
                pygame.Rect(x + width + gap, y, width, height),
                "PAUSE",
                self.toggle_pause,
                enabled=enabled,
            ),
            ActionButton(
                pygame.Rect(x + (width + gap) * 2, y, width, height),
                "RESET",
                self.reset_rom,
                enabled=enabled,
            ),
            ActionButton(
                pygame.Rect(x, y + 47, width, height),
                "QUICK SAVE",
                self.quick_save,
                enabled=enabled,
            ),
            ActionButton(
                pygame.Rect(x + width + gap, y + 47, width, height),
                "QUICK LOAD",
                self.quick_load,
                enabled=lambda: self.has_rom and self.quick_state is not None,
            ),
            ActionButton(
                pygame.Rect(x + (width + gap) * 2, y + 47, width, height),
                "MUTE",
                self.toggle_mute,
                enabled=lambda: self.audio.available,
            ),
            ActionButton(
                pygame.Rect(x, y + 94, 155, height),
                "ABOUT",
                self.toggle_about,
            ),
            ActionButton(
                pygame.Rect(x + 163, y + 94, 155, height),
                "EXIT",
                self.request_exit,
            ),
        ]

    def _build_controller_regions(self) -> dict[str, pygame.Rect]:
        return {
            "up": pygame.Rect(615, 371, 42, 42),
            "left": pygame.Rect(573, 413, 42, 42),
            "right": pygame.Rect(657, 413, 42, 42),
            "down": pygame.Rect(615, 455, 42, 42),
            "b": pygame.Rect(765, 426, 54, 54),
            "a": pygame.Rect(832, 397, 54, 54),
            "select": pygame.Rect(735, 508, 67, 25),
            "start": pygame.Rect(813, 508, 67, 25),
        }

    def set_status(
        self,
        text: str,
        color: tuple[int, int, int] = SOFT_BLUE,
        seconds: float = 4.0,
    ) -> None:
        self.status_text = text.upper()
        self.status_color = color
        self.status_until = time.monotonic() + seconds if seconds else 0.0

    def choose_rom(self) -> None:
        self.audio.clear()
        try:
            if IS_MACOS:
                filename = self._choose_rom_macos()
            else:
                filename = self._choose_rom_tk()
            if filename:
                self.load_rom(filename)
        except Exception as exc:
            self.set_status(f"ROM PICKER ERROR: {exc}", ERROR, 7.0)

    @staticmethod
    def _choose_rom_macos() -> str:
        """Use macOS Standard Additions without loading Tk into this process."""
        script = """
on run
    try
        set romFile to choose file with prompt "Load a Game Boy ROM (.gb or .gbc)" \
            of type {"gb", "gbc"}
        return POSIX path of romFile
    on error number -128
        return ""
    end try
end run
"""
        result = subprocess.run(
            ["osascript", "-e", script],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip().splitlines()
            raise RuntimeError(detail[-1] if detail else "native file dialog failed")
        return result.stdout.strip()

    @staticmethod
    def _choose_rom_tk() -> str:
        root = None
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            try:
                root.attributes("-topmost", True)
            except tk.TclError:
                pass
            root.update()
            filename = filedialog.askopenfilename(
                parent=root,
                title="Load Game Boy ROM",
                filetypes=[
                    ("Game Boy ROMs", "*.gb *.gbc"),
                    ("Game Boy", "*.gb"),
                    ("Game Boy Color", "*.gbc"),
                    ("All files", "*.*"),
                ],
            )
            return filename
        finally:
            if root is not None:
                root.destroy()

    def _validate_rom(self, path: Path) -> None:
        if path.suffix.lower() not in SUPPORTED_ROM_EXTENSIONS:
            raise ValueError("select a .gb or .gbc ROM")
        if not path.is_file():
            raise FileNotFoundError("ROM file was not found")
        if path.stat().st_size < 0x150:
            raise ValueError("file is too small to be a Game Boy ROM")

    def _new_pyboy(self, path: Path) -> PyBoy:
        emulator = PyBoy(
            str(path),
            window="null",
            sound_emulated=True,
            sound_volume=100,
            sound_sample_rate=48_000,
            log_level="WARNING",
        )
        # The null renderer defaults to unlimited. This GUI supplies one Game
        # Boy frame per 60 FPS update, so internal sleeping must stay disabled.
        emulator.set_emulation_speed(0)
        return emulator

    def load_rom(self, filename: str | os.PathLike[str]) -> None:
        path = Path(filename).expanduser()
        try:
            self._validate_rom(path)
            replacement = self._new_pyboy(path)
        except Exception as exc:
            self.set_status(f"LOAD FAILED: {exc}", ERROR, 8.0)
            return

        old_emulator = self.pyboy
        self.pyboy = replacement
        self.rom_path = path
        self.rom_name = path.name
        self.game_title = str(getattr(replacement, "cartridge_title", path.stem))
        self.paused = False
        self.quick_state = None
        self.accumulator = 0.0
        self.frame_surface = None
        self._release_all_inputs()
        self.audio.clear()
        self.set_status(f"LOADED: {self.rom_name}", SUCCESS, 5.0)

        if old_emulator is not None:
            try:
                old_emulator.stop(save=True)
            except Exception:
                pass

    def unload_rom(self, message: str = "EMULATION STOPPED") -> None:
        old_emulator = self.pyboy
        self.pyboy = None
        self.rom_path = None
        self.rom_name = "NO CARTRIDGE"
        self.game_title = "WAITING FOR ROM"
        self.frame_surface = None
        self.quick_state = None
        self.paused = False
        self._release_all_inputs()
        self.audio.clear()
        if old_emulator is not None:
            try:
                old_emulator.stop(save=True)
            except Exception:
                pass
        self.set_status(message, WARNING, 6.0)

    def reset_rom(self) -> None:
        if self.rom_path is None:
            return
        path = self.rom_path
        self.set_status("RESETTING CARTRIDGE...", WARNING, 2.0)
        # Flush battery-backed cartridge RAM before recreating the core, so a
        # reset cannot restart from an older on-disk save.
        self._release_all_inputs()
        self.audio.clear()
        old_emulator = self.pyboy
        self.pyboy = None
        if old_emulator is not None:
            try:
                old_emulator.stop(save=True)
            except Exception:
                pass
        self.load_rom(path)

    def toggle_pause(self) -> None:
        if not self.has_rom:
            return
        self.paused = not self.paused
        self.accumulator = 0.0
        if self.paused:
            self.audio.clear()
            self._release_all_inputs()
            self.set_status("PAUSED", WARNING, 0.0)
        else:
            self.set_status("RUNNING AT GAME BOY SPEED", SUCCESS, 3.0)

    def quick_save(self) -> None:
        if self.pyboy is None:
            return
        try:
            state = io.BytesIO()
            self.pyboy.save_state(state)
            state.seek(0)
            self.quick_state = state
            self.set_status("QUICK STATE SAVED IN MEMORY", SUCCESS, 4.0)
        except Exception as exc:
            self.set_status(f"SAVE FAILED: {exc}", ERROR, 6.0)

    def quick_load(self) -> None:
        if self.pyboy is None or self.quick_state is None:
            return
        try:
            self.quick_state.seek(0)
            self.pyboy.load_state(self.quick_state)
            self._release_all_inputs()
            self.accumulator = 0.0
            self._capture_frame()
            self.set_status("QUICK STATE LOADED", SUCCESS, 4.0)
        except Exception as exc:
            self.set_status(f"LOAD STATE FAILED: {exc}", ERROR, 6.0)

    def toggle_mute(self) -> None:
        muted = self.audio.toggle_mute()
        self.set_status("AUDIO MUTED" if muted else "AUDIO ENABLED", WARNING if muted else SUCCESS)

    def toggle_about(self) -> None:
        self.show_about = not self.show_about

    def request_exit(self) -> None:
        self.running = False

    def _press_input(self, name: str) -> None:
        if self.pyboy is None or self.paused or name in self.held_inputs:
            return
        try:
            self.pyboy.button_press(name)
            self.held_inputs.add(name)
        except Exception as exc:
            self.set_status(f"INPUT ERROR: {exc}", ERROR, 4.0)

    def _release_input(self, name: str) -> None:
        if name not in self.held_inputs:
            return
        if self.pyboy is not None:
            try:
                self.pyboy.button_release(name)
            except Exception:
                pass
        self.held_inputs.discard(name)

    def _release_all_inputs(self) -> None:
        for name in tuple(self.held_inputs):
            self._release_input(name)
        self.pointer_input = None

    def _keyboard_input(self, key: int) -> str | None:
        return {
            pygame.K_LEFT: "left",
            pygame.K_RIGHT: "right",
            pygame.K_UP: "up",
            pygame.K_DOWN: "down",
            pygame.K_z: "b",
            pygame.K_x: "a",
            pygame.K_BACKSPACE: "select",
            pygame.K_RETURN: "start",
        }.get(key)

    def _handle_keydown(self, event: pygame.event.Event) -> None:
        modifiers = pygame.key.get_mods()
        if event.key == pygame.K_o and modifiers & (pygame.KMOD_CTRL | pygame.KMOD_META):
            self.choose_rom()
        elif event.key == pygame.K_p:
            self.toggle_pause()
        elif event.key == pygame.K_F5:
            self.quick_save()
        elif event.key == pygame.K_F8:
            self.quick_load()
        elif event.key == pygame.K_m:
            self.toggle_mute()
        elif event.key == pygame.K_ESCAPE and self.show_about:
            self.show_about = False
        else:
            name = self._keyboard_input(event.key)
            if name:
                self._press_input(name)

    def _handle_mouse_down(self, position: tuple[int, int]) -> None:
        if self.show_about:
            self.show_about = False
            return
        for button in self.action_buttons:
            if button.click(position):
                return
        for name, rect in self.controller_regions.items():
            if rect.collidepoint(position):
                self.pointer_input = name
                self._press_input(name)
                return

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.DROPFILE:
                self.load_rom(event.file)
            elif event.type == pygame.KEYDOWN:
                self._handle_keydown(event)
            elif event.type == pygame.KEYUP:
                name = self._keyboard_input(event.key)
                if name:
                    self._release_input(name)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_mouse_down(event.pos)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if self.pointer_input:
                    self._release_input(self.pointer_input)
                    self.pointer_input = None
            elif event.type == pygame.WINDOWFOCUSLOST:
                self._release_all_inputs()
                self.audio.clear()

    def emulate(self, elapsed: float) -> None:
        if self.pyboy is None or self.paused:
            return

        self.accumulator += min(elapsed, 0.100)
        frames_due = min(int(self.accumulator / GAMEBOY_FRAME_TIME), 4)
        if frames_due <= 0:
            return

        try:
            alive = self.pyboy.tick(
                frames_due,
                render=True,
                sound=not self.audio.muted and self.audio.available,
            )
            self.accumulator -= frames_due * GAMEBOY_FRAME_TIME
            if not alive:
                self.unload_rom("THE EMULATOR CORE REQUESTED EXIT")
                return
            self._capture_frame()
            if self.audio.available and not self.audio.muted:
                self.audio.feed(self.pyboy.sound.ndarray)
        except Exception as exc:
            traceback.print_exc()
            self.unload_rom(f"EMULATION ERROR: {exc}")

    def _capture_frame(self) -> None:
        if self.pyboy is None:
            return
        frame = self.pyboy.screen.ndarray
        try:
            native = pygame.image.frombuffer(frame, (160, 144), "RGBA").copy()
        except (TypeError, ValueError, pygame.error):
            native = pygame.image.fromstring(frame.tobytes(), (160, 144), "RGBA")
        self.frame_surface = pygame.transform.scale(native, self.screen_rect.size)

    def _draw_header(self) -> None:
        draw_text(self.window, self.font_title, "AC'S PYBOY", BRIGHT_BLUE, (48, 22))
        draw_text(self.window, self.font_heading, "GB EMULATOR 0.1.1", BLUE, (286, 30))
        draw_text(
            self.window,
            self.font_small,
            "PYTHON 3.14  /  60 FPS UI  /  60 FPS GAME BOY CORE",
            SOFT_BLUE,
            (48, 70),
        )
        pygame.draw.line(self.window, DIM_BLUE, (48, 91), (912, 91), 1)

    def _draw_display(self) -> None:
        bezel = self.screen_rect.inflate(24, 24)
        rounded_panel(self.window, bezel, INK, BLUE, 15)
        pygame.draw.rect(self.window, (0, 0, 0), self.screen_rect)

        if self.frame_surface is not None:
            self.window.blit(self.frame_surface, self.screen_rect)
        else:
            for y in range(self.screen_rect.top, self.screen_rect.bottom, 4):
                shade = 11 + ((y // 4) % 2) * 3
                pygame.draw.line(
                    self.window,
                    (3, shade + 7, shade + 20),
                    (self.screen_rect.left, y),
                    (self.screen_rect.right - 1, y),
                )
            draw_text(
                self.window,
                self.font_heading,
                "INSERT CARTRIDGE",
                BLUE,
                self.screen_rect.center,
                anchor="center",
            )
            draw_text(
                self.window,
                self.font_small,
                "CLICK LOAD ROM OR DROP A .GB / .GBC FILE",
                SOFT_BLUE,
                (self.screen_rect.centerx, self.screen_rect.centery + 37),
                anchor="center",
            )

        if self.paused and self.frame_surface is not None:
            overlay = pygame.Surface(self.screen_rect.size, pygame.SRCALPHA)
            overlay.fill((0, 8, 20, 175))
            self.window.blit(overlay, self.screen_rect)
            draw_text(
                self.window,
                self.font_title,
                "PAUSED",
                BRIGHT_BLUE,
                self.screen_rect.center,
                anchor="center",
            )

    def _draw_status_card(self) -> None:
        card = pygame.Rect(570, 260, 324, 76)
        rounded_panel(self.window, card, BACKGROUND, DIM_BLUE, 9)
        light = SUCCESS if self.has_rom and not self.paused else (WARNING if self.paused else DIM_BLUE)
        pygame.draw.circle(self.window, light, (587, 279), 5)
        draw_text(
            self.window,
            self.font_body,
            self.game_title[:24],
            OFF_WHITE if self.has_rom else SOFT_BLUE,
            (600, 268),
        )
        draw_text(self.window, self.font_small, self.rom_name[:38], SOFT_BLUE, (584, 294))
        state = "PAUSED" if self.paused else ("RUNNING" if self.has_rom else "IDLE")
        audio = "MUTED" if self.audio.muted else ("AUDIO" if self.audio.available else "NO AUDIO")
        draw_text(
            self.window,
            self.font_small,
            f"{state}  |  {audio}  |  {self.fps:04.1f} FPS",
            BLUE,
            (584, 314),
        )

    def _draw_controller(self, mouse: tuple[int, int]) -> None:
        draw_text(self.window, self.font_small, "VIRTUAL CONTROLS", SOFT_BLUE, (570, 349))

        for name in ("up", "left", "right", "down"):
            rect = self.controller_regions[name]
            pressed = name in self.held_inputs
            hover = rect.collidepoint(mouse) and self.has_rom
            fill = PANEL_LIGHT if pressed else (BLACK_BUTTON_HOVER if hover else BLACK_BUTTON)
            border = BRIGHT_BLUE if pressed or hover else DIM_BLUE
            pygame.draw.rect(self.window, fill, rect, border_radius=6)
            pygame.draw.rect(self.window, border, rect, width=2, border_radius=6)
            glyph = {"up": "^", "left": "<", "right": ">", "down": "v"}[name]
            draw_text(self.window, self.font_heading, glyph, border, rect.center, anchor="center")

        for name in ("b", "a"):
            rect = self.controller_regions[name]
            pressed = name in self.held_inputs
            hover = rect.collidepoint(mouse) and self.has_rom
            fill = PANEL_LIGHT if pressed else (BLACK_BUTTON_HOVER if hover else BLACK_BUTTON)
            border = BRIGHT_BLUE if pressed or hover else BLUE
            pygame.draw.ellipse(self.window, fill, rect)
            pygame.draw.ellipse(self.window, border, rect, width=2)
            draw_text(self.window, self.font_heading, name.upper(), border, rect.center, anchor="center")

        for name in ("select", "start"):
            rect = self.controller_regions[name]
            pressed = name in self.held_inputs
            hover = rect.collidepoint(mouse) and self.has_rom
            fill = PANEL_LIGHT if pressed else (BLACK_BUTTON_HOVER if hover else BLACK_BUTTON)
            border = BRIGHT_BLUE if pressed or hover else DIM_BLUE
            pygame.draw.rect(self.window, fill, rect, border_radius=12)
            pygame.draw.rect(self.window, border, rect, width=1, border_radius=12)
            draw_text(self.window, self.font_small, name.upper(), border, rect.center, anchor="center")

    def _draw_footer(self) -> None:
        if self.status_until and time.monotonic() > self.status_until:
            self.status_text = "READY  |  CTRL+O LOAD  |  P PAUSE  |  F5 SAVE  |  F8 LOAD"
            self.status_color = SOFT_BLUE
            self.status_until = 0.0
        pygame.draw.line(self.window, DIM_BLUE, (48, 579), (912, 579), 1)
        draw_text(self.window, self.font_small, self.status_text[:95], self.status_color, (48, 592))
        draw_text(
            self.window,
            self.font_small,
            "ARROWS: D-PAD   Z: B   X: A   BACKSPACE: SELECT   ENTER: START",
            DIM_BLUE,
            (48, 616),
        )

    def _draw_about(self) -> None:
        shade = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
        shade.fill((0, 4, 12, 210))
        self.window.blit(shade, (0, 0))
        box = pygame.Rect(205, 135, 550, 360)
        rounded_panel(self.window, box, PANEL, BRIGHT_BLUE, 16)
        draw_text(self.window, self.font_title, "AC'S PYBOY", BRIGHT_BLUE, (480, 174), anchor="center")
        draw_text(self.window, self.font_heading, "GB EMULATOR 0.1.1", BLUE, (480, 210), anchor="center")
        lines = [
            "Original single-file blue-hue frontend",
            "PyBoy core  |  pygame-ce interface  |  Python 3.14+",
            "Game Boy and Game Boy Color ROM support",
            "60 FPS interface with a 60 FPS Game Boy core",
            "Quick states are kept in memory for this session",
            "",
            "No ROM, BIOS, image, or font files are bundled.",
            "Use only game dumps you are legally entitled to use.",
        ]
        for index, line in enumerate(lines):
            draw_text(
                self.window,
                self.font_body,
                line,
                OFF_WHITE if index in (0, 6, 7) else SOFT_BLUE,
                (480, 252 + index * 27),
                anchor="center",
            )
        draw_text(self.window, self.font_small, "CLICK ANYWHERE OR PRESS ESC TO CLOSE", BLUE, (480, 468), anchor="center")

    def draw(self) -> None:
        self.window.fill(BACKGROUND)
        mouse = pygame.mouse.get_pos()
        self._draw_header()
        self._draw_display()
        rounded_panel(self.window, self.control_panel, PANEL, DIM_BLUE, 14)
        for button in self.action_buttons:
            if button.label == "PAUSE":
                button.label = "RESUME" if self.paused else "PAUSE"
            elif button.label in ("MUTE", "UNMUTE"):
                button.label = "UNMUTE" if self.audio.muted else "MUTE"
            button.draw(self.window, self.font_button, mouse)
        self._draw_status_card()
        self._draw_controller(mouse)
        self._draw_footer()
        if self.show_about:
            self._draw_about()
        pygame.display.flip()

    def shutdown(self) -> None:
        self._release_all_inputs()
        self.audio.clear()
        if self.pyboy is not None:
            try:
                self.pyboy.stop(save=True)
            except Exception:
                pass
        pygame.quit()

    def run(self) -> None:
        try:
            while self.running:
                elapsed = self.clock.tick(UI_FPS) / 1000.0
                self.fps = self.clock.get_fps()
                self.handle_events()
                self.emulate(elapsed)
                self.draw()
        finally:
            self.shutdown()


def initial_rom_from_arguments() -> str | None:
    for argument in sys.argv[1:]:
        if argument.startswith("-"):
            continue
        path = Path(argument).expanduser()
        if path.suffix.lower() in SUPPORTED_ROM_EXTENSIONS:
            return str(path)
    return None


def main() -> int:
    app = EmulatorApp(initial_rom_from_arguments())
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
