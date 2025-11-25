"""
VanillaChanny GUI Desktop Application
Standalone speech recognition and subtitle application with OBS integration
"""

import customtkinter as ctk
import sounddevice as sd
import threading
import queue
import json
from pathlib import Path
from typing import Optional, Dict, Any
import time
from tqdm import tqdm
import traceback
from tkinter import messagebox, colorchooser
import shutil

# Import our existing components
from speech_capture import Config, AudioCapture, SpeechRecognizer
from setup_wizard import SetupWizard
from loading_dialog import LoadingDialog
from language_manager import LanguageManager
from language_dialog import LanguageSelectionDialog
from translator import Translator
import browser_server


class DownloadProgressBar(tqdm):
    """Custom tqdm progress bar that updates loading dialog"""

    def __init__(self, *args, loading_dialog=None, **kwargs):
        self.loading_dialog = loading_dialog
        self.last_update = time.time()
        self.update_interval = 0.1  # Update every 100ms
        super().__init__(*args, **kwargs)

    def update(self, n=1):
        super().update(n)

        # Throttle updates to avoid overwhelming GUI
        now = time.time()
        if self.loading_dialog and (now - self.last_update) > self.update_interval:
            self.last_update = now

            # Calculate download speed
            if hasattr(self, 'start_t') and self.n > 0:
                elapsed = now - self.start_t
                if elapsed > 0:
                    speed = self.n / elapsed  # bytes per second
                else:
                    speed = 0
            else:
                speed = 0

            # Update dialog
            if self.total:
                self.loading_dialog.after(0, lambda: self.loading_dialog.update_progress(
                    int(self.n), int(self.total), speed
                ))


class AudioLevelMeter(ctk.CTkFrame):
    """Visual audio level meter with dB scale"""

    def __init__(self, master, lang_manager=None, **kwargs):
        super().__init__(master, **kwargs)

        self.lang = lang_manager
        self.level = -100  # Current dB level
        self.gate_threshold = -40
        self.gate_open = False

        # Create canvas for meter
        self.canvas = ctk.CTkCanvas(self, width=300, height=60, bg="#2b2b2b", highlightthickness=0)
        self.canvas.pack(padx=10, pady=10)

        # Labels
        self.level_label = ctk.CTkLabel(self, text="-100 dB", font=("Arial", 12))
        self.level_label.pack()

        self.gate_status = ctk.CTkLabel(self, text=self._get_gate_text(), font=("Arial", 12))
        self.gate_status.pack()

        self.update_display()

    def _get_gate_text(self):
        """Get translated gate status text"""
        if self.lang:
            if self.gate_open:
                return f"🟢 {self.lang.get('gate_open')}"
            else:
                return f"⚫ {self.lang.get('gate_closed')}"
        else:
            return "🟢 Gate: OPEN" if self.gate_open else "⚫ Gate: CLOSED"

    def update_level(self, db_level: float, gate_is_open: bool):
        """Update the meter with new audio level"""
        self.level = db_level
        self.gate_open = gate_is_open
        self.update_display()

    def update_display(self):
        """Redraw the meter"""
        self.canvas.delete("all")

        # Draw background
        self.canvas.create_rectangle(10, 10, 290, 50, fill="#1a1a1a", outline="#444")

        # Calculate bar width (dB range: -60 to 0)
        db_normalized = max(0, min(1, (self.level + 60) / 60))
        bar_width = int(270 * db_normalized)

        # Color based on level
        if self.level > -10:
            color = "#ff0000"  # Red (too loud)
        elif self.level > -20:
            color = "#ffaa00"  # Orange
        elif self.level > -40:
            color = "#00ff00"  # Green (good)
        else:
            color = "#004400"  # Dark green (quiet)

        # Draw level bar
        if bar_width > 0:
            self.canvas.create_rectangle(10, 10, 10 + bar_width, 50, fill=color, outline="")

        # Draw threshold line
        threshold_x = int(10 + 270 * ((self.gate_threshold + 60) / 60))
        self.canvas.create_line(threshold_x, 10, threshold_x, 50, fill="#ffff00", width=2)

        # Update labels
        self.level_label.configure(text=f"{self.level:.1f} dB")

        if self.gate_open:
            self.gate_status.configure(text=self._get_gate_text(), text_color="#00ff00")
        else:
            self.gate_status.configure(text=self._get_gate_text(), text_color="#666666")


class MainApplication(ctk.CTk):
    """Main GUI Application Window"""

    def __init__(self):
        super().__init__()

        # Set theme first
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Window setup first
        self.geometry("800x700")

        # Load or create config
        self.config = Config()

        # Language setup - show selection dialog on first launch
        gui_language = self.config.config.get("gui", {}).get("language")
        first_launch = self.config.config.get("gui", {}).get("first_launch", True)

        if first_launch or gui_language is None:
            # Show language selection dialog
            # Use after() to show dialog after window is ready
            self.after(100, self.show_first_launch_language_dialog)

            # Use English as default until selection
            gui_language = "en"

        # Initialize language manager
        try:
            self.lang = LanguageManager(gui_language)
            print(f"Initialized language: {self.lang.get_language_name()}")
        except Exception as e:
            print(f"Error loading language: {e}")
            print("Falling back to English")
            self.lang = LanguageManager("en")

        # Set title
        self.title(self.lang.get("app_title"))

        # State
        self.is_running = False
        self.audio_capture = None
        self.recognizer = None
        self.translator = Translator()
        self.monitor_thread = None
        self.stop_monitoring = threading.Event()

        # Start browser output server
        self.browser_server_thread = None
        self.start_browser_server()

        # Create UI
        self.create_ui()

        # Protocol for window close
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_ui(self):
        """Create the user interface"""

        # Top bar with title and language switcher
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.pack(fill="x", pady=10)

        # Title
        self.title_label = ctk.CTkLabel(
            top_bar,
            text=self.lang.get("app_header"),
            font=("Arial", 24, "bold")
        )
        self.title_label.pack(side="left", padx=20)

        # Language switcher button
        self.lang_button = ctk.CTkButton(
            top_bar,
            text=self.lang.get("buttons.language") + f" {self.lang.get_language_name()}",
            command=self.show_language_menu,
            width=150,
            height=35,
            font=("Arial", 14),
            fg_color="#666666",
            hover_color="#888888"
        )
        self.lang_button.pack(side="right", padx=20)

        # Main container
        container = ctk.CTkFrame(self)
        container.pack(fill="both", expand=True, padx=20, pady=10)

        # Left panel - Tabbed Settings
        left_panel = ctk.CTkFrame(container)
        left_panel.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        # Settings header
        self.settings_header = ctk.CTkLabel(left_panel, text=self.lang.get("settings"), font=("Arial", 18, "bold"))
        self.settings_header.pack(pady=10)

        # Create tabview
        self.tabview = ctk.CTkTabview(left_panel)
        self.tabview.pack(fill="both", expand=True, padx=5, pady=5)

        # Add tabs
        self.tab_recognition = self.tabview.add(self.lang.get("tab_recognition"))
        self.tab_output = self.tabview.add(self.lang.get("tab_output"))

        # Create scrollable frames inside each tab
        self.recognition_scroll = ctk.CTkScrollableFrame(self.tab_recognition)
        self.recognition_scroll.pack(fill="both", expand=True, padx=5, pady=5)

        self.output_scroll = ctk.CTkScrollableFrame(self.tab_output)
        self.output_scroll.pack(fill="both", expand=True, padx=5, pady=5)

        # Populate tabs
        self.create_recognition_panel(self.recognition_scroll)
        self.create_output_panel(self.output_scroll)

        # Right panel - Monitor
        right_panel = ctk.CTkFrame(container)
        right_panel.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        self.create_monitor_panel(right_panel)

        # Bottom panel - Controls
        control_panel = ctk.CTkFrame(self)
        control_panel.pack(fill="x", padx=20, pady=10)

        self.create_control_panel(control_panel)

    def create_recognition_panel(self, parent):
        """Create recognition settings panel (Tab 1)"""

        # Audio Device Selection
        device_frame = ctk.CTkFrame(parent)
        device_frame.pack(fill="x", padx=10, pady=5)

        self.audio_device_label = ctk.CTkLabel(device_frame, text=self.lang.get("audio_device"), font=("Arial", 12))
        self.audio_device_label.pack(anchor="w", padx=5, pady=5)

        # Get available devices
        devices = sd.query_devices()
        input_devices = [f"{i}: {d['name']}" for i, d in enumerate(devices) if d['max_input_channels'] > 0]

        self.device_var = ctk.StringVar(value=input_devices[0] if input_devices else "No devices")
        device_menu = ctk.CTkOptionMenu(
            device_frame,
            variable=self.device_var,
            values=input_devices,
            command=self.on_device_change
        )
        device_menu.pack(fill="x", padx=5, pady=5)

        # Noise Gate Settings
        gate_frame = ctk.CTkFrame(parent)
        gate_frame.pack(fill="x", padx=10, pady=10)

        self.noise_gate_label = ctk.CTkLabel(gate_frame, text=self.lang.get("noise_gate"), font=("Arial", 14, "bold"))
        self.noise_gate_label.pack(pady=5)

        # Threshold slider
        self.threshold_label = ctk.CTkLabel(gate_frame, text=self.lang.get("threshold_value", value=-40))
        self.threshold_label.pack(anchor="w", padx=5)

        self.threshold_var = ctk.IntVar(value=-40)
        threshold_slider = ctk.CTkSlider(
            gate_frame,
            from_=-60,
            to=-20,
            variable=self.threshold_var,
            command=lambda v: self.update_threshold_label(self.threshold_label, v)
        )
        threshold_slider.pack(fill="x", padx=5, pady=5)

        # Release time slider
        self.release_label = ctk.CTkLabel(gate_frame, text=self.lang.get("release_time_value", value=0.8))
        self.release_label.pack(anchor="w", padx=5)

        self.release_var = ctk.DoubleVar(value=0.8)
        release_slider = ctk.CTkSlider(
            gate_frame,
            from_=0.2,
            to=2.0,
            variable=self.release_var,
            command=lambda v: self.update_release_label(self.release_label, v)
        )
        release_slider.pack(fill="x", padx=5, pady=5)

        # Model Settings
        model_frame = ctk.CTkFrame(parent)
        model_frame.pack(fill="x", padx=10, pady=10)

        self.model_label = ctk.CTkLabel(model_frame, text=self.lang.get("model_settings"), font=("Arial", 14, "bold"))
        self.model_label.pack(pady=5)

        self.model_var = ctk.StringVar(value="small")
        models = ["tiny", "base", "small", "medium", "large"]
        model_menu = ctk.CTkOptionMenu(
            model_frame,
            variable=self.model_var,
            values=models,
            command=self.on_model_change
        )
        model_menu.pack(fill="x", padx=5, pady=5)

        # Languages Section
        lang_section = ctk.CTkFrame(parent)
        lang_section.pack(fill="x", padx=10, pady=10)

        self.languages_header_label = ctk.CTkLabel(lang_section, text=self.lang.get("languages_section"), font=("Arial", 14, "bold"))
        self.languages_header_label.pack(pady=5)

        # Main Language (Speech Recognition)
        main_lang_frame = ctk.CTkFrame(lang_section)
        main_lang_frame.pack(fill="x", padx=5, pady=3)

        self.main_language_label = ctk.CTkLabel(main_lang_frame, text=self.lang.get("main_language"), font=("Arial", 12))
        self.main_language_label.pack(anchor="w", padx=5, pady=2)

        # Load from config
        saved_lang = self.config.config.get("whisper", {}).get("language", "en")
        if saved_lang is None:
            saved_lang = "auto"
        self.lang_var = ctk.StringVar(value=saved_lang)
        languages = ["en", "ja", "es", "fr", "de", "it", "pt", "zh", "ko", "auto"]
        lang_menu = ctk.CTkOptionMenu(
            main_lang_frame,
            variable=self.lang_var,
            values=languages,
            command=self.on_recog_language_change
        )
        lang_menu.pack(fill="x", padx=5, pady=2)

        # Translated Language 1
        trans1_frame = ctk.CTkFrame(lang_section)
        trans1_frame.pack(fill="x", padx=5, pady=3)

        self.trans1_label = ctk.CTkLabel(trans1_frame, text=self.lang.get("translated_language_1"), font=("Arial", 12))
        self.trans1_label.pack(anchor="w", padx=5, pady=2)

        # Load from config
        saved_trans1 = self.config.config.get("translation", {}).get("target_language_1", None)
        if saved_trans1 is None:
            saved_trans1 = "none"
        self.trans1_var = ctk.StringVar(value=saved_trans1)
        translation_languages = ["none", "en", "ja", "es", "fr", "de", "it", "pt", "zh", "ko"]
        trans1_menu = ctk.CTkOptionMenu(
            trans1_frame,
            variable=self.trans1_var,
            values=translation_languages,
            command=self.on_trans1_change
        )
        trans1_menu.pack(fill="x", padx=5, pady=2)

        # Translated Language 2
        trans2_frame = ctk.CTkFrame(lang_section)
        trans2_frame.pack(fill="x", padx=5, pady=3)

        self.trans2_label = ctk.CTkLabel(trans2_frame, text=self.lang.get("translated_language_2"), font=("Arial", 12))
        self.trans2_label.pack(anchor="w", padx=5, pady=2)

        # Load from config
        saved_trans2 = self.config.config.get("translation", {}).get("target_language_2", None)
        if saved_trans2 is None:
            saved_trans2 = "none"
        self.trans2_var = ctk.StringVar(value=saved_trans2)
        trans2_menu = ctk.CTkOptionMenu(
            trans2_frame,
            variable=self.trans2_var,
            values=translation_languages,
            command=self.on_trans2_change
        )
        trans2_menu.pack(fill="x", padx=5, pady=2)

    def create_output_panel(self, parent):
        """Create output settings panel (Tab 2)"""

        # Output Settings Section
        output_section = ctk.CTkFrame(parent)
        output_section.pack(fill="x", padx=10, pady=10)

        self.output_settings_label = ctk.CTkLabel(output_section, text=self.lang.get("output_settings"), font=("Arial", 14, "bold"))
        self.output_settings_label.pack(pady=5)

        # Output language selection checkboxes
        checkbox_frame = ctk.CTkFrame(output_section)
        checkbox_frame.pack(fill="x", padx=5, pady=5)

        # Load from config
        output_config = self.config.config.get("output", {})

        self.output_main_var = ctk.BooleanVar(value=output_config.get("show_main", True))
        self.output_trans1_var = ctk.BooleanVar(value=output_config.get("show_translation_1", False))
        self.output_trans2_var = ctk.BooleanVar(value=output_config.get("show_translation_2", False))

        self.output_main_checkbox = ctk.CTkCheckBox(
            checkbox_frame,
            text=self.lang.get("output_main"),
            variable=self.output_main_var,
            command=self.on_output_setting_change
        )
        self.output_main_checkbox.pack(anchor="w", padx=10, pady=3)

        self.output_trans1_checkbox = ctk.CTkCheckBox(
            checkbox_frame,
            text=self.lang.get("output_trans1"),
            variable=self.output_trans1_var,
            command=self.on_output_setting_change
        )
        self.output_trans1_checkbox.pack(anchor="w", padx=10, pady=3)

        self.output_trans2_checkbox = ctk.CTkCheckBox(
            checkbox_frame,
            text=self.lang.get("output_trans2"),
            variable=self.output_trans2_var,
            command=self.on_output_setting_change
        )
        self.output_trans2_checkbox.pack(anchor="w", padx=10, pady=3)

        # Output method selection
        method_frame = ctk.CTkFrame(output_section)
        method_frame.pack(fill="x", padx=5, pady=5)

        self.output_method_label = ctk.CTkLabel(method_frame, text=self.lang.get("output_method"), font=("Arial", 12))
        self.output_method_label.pack(anchor="w", padx=5, pady=2)

        saved_method = output_config.get("method", "browser")
        self.output_method_var = ctk.StringVar(value=saved_method)
        output_methods = ["browser", "file", "webhook"]
        method_menu = ctk.CTkOptionMenu(
            method_frame,
            variable=self.output_method_var,
            values=output_methods,
            command=self.on_output_method_change
        )
        method_menu.pack(fill="x", padx=5, pady=2)

        self.output_note_label = ctk.CTkLabel(
            output_section,
            text=self.lang.get("output_note"),
            font=("Arial", 10),
            text_color="#888888"
        )
        self.output_note_label.pack(pady=3)

        # Browser Output Section
        browser_section = ctk.CTkFrame(parent)
        browser_section.pack(fill="x", padx=10, pady=10)

        self.browser_output_label = ctk.CTkLabel(
            browser_section,
            text=self.lang.get("browser_output.title"),
            font=("Arial", 14, "bold")
        )
        self.browser_output_label.pack(pady=5)

        # URL Display
        url_frame = ctk.CTkFrame(browser_section)
        url_frame.pack(fill="x", padx=5, pady=5)

        self.url_label = ctk.CTkLabel(
            url_frame,
            text=self.lang.get("browser_output.url_label"),
            font=("Arial", 12)
        )
        self.url_label.pack(anchor="w", padx=5, pady=2)

        browser_port = self.config.config.get("browser_output", {}).get("port", 8765)
        self.browser_url = f"http://127.0.0.1:{browser_port}"

        url_display_frame = ctk.CTkFrame(url_frame)
        url_display_frame.pack(fill="x", padx=5, pady=2)

        self.url_text = ctk.CTkEntry(
            url_display_frame,
            font=("Arial", 11),
            state="readonly"
        )
        self.url_text.configure(state="normal")
        self.url_text.insert(0, self.browser_url)
        self.url_text.configure(state="readonly")
        self.url_text.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.copy_url_button = ctk.CTkButton(
            url_display_frame,
            text=self.lang.get("browser_output.copy_url"),
            command=self.copy_url_to_clipboard,
            width=120
        )
        self.copy_url_button.pack(side="right")

        # Font list
        fonts = ["Arial", "Helvetica", "Times New Roman", "Courier New", "Comic Sans MS",
                 "Impact", "Georgia", "Verdana", "Trebuchet MS", "MS Gothic", "Yu Gothic"]

        # Main Language Styling
        main_styling_frame = ctk.CTkFrame(browser_section)
        main_styling_frame.pack(fill="x", padx=5, pady=5)

        self.main_styling_label = ctk.CTkLabel(
            main_styling_frame,
            text=self.lang.get("browser_output.main_styling"),
            font=("Arial", 12, "bold")
        )
        self.main_styling_label.pack(anchor="w", padx=5, pady=3)

        main_config = self.config.config.get("browser_output", {}).get("main", {})

        main_controls = ctk.CTkFrame(main_styling_frame)
        main_controls.pack(fill="x", padx=10, pady=3)

        self.main_font_label = ctk.CTkLabel(main_controls, text=self.lang.get("browser_output.font"))
        self.main_font_label.grid(row=0, column=0, sticky="w", padx=5, pady=2)

        self.main_font_var = ctk.StringVar(value=main_config.get("font", "Arial"))
        main_font_menu = ctk.CTkOptionMenu(
            main_controls,
            variable=self.main_font_var,
            values=fonts,
            command=lambda v: self.on_browser_style_change("main", "font", v)
        )
        main_font_menu.grid(row=0, column=1, sticky="ew", padx=5, pady=2)

        # Font Size Slider
        ctk.CTkLabel(main_controls, text="Font Size:").grid(row=1, column=0, sticky="w", padx=5, pady=2)

        self.main_size_var = ctk.IntVar(value=main_config.get("font_size", 32))
        self.main_size_label = ctk.CTkLabel(main_controls, text=f"{self.main_size_var.get()}px")
        self.main_size_label.grid(row=1, column=1, sticky="w", padx=5, pady=2)

        main_size_slider = ctk.CTkSlider(
            main_controls,
            from_=16,
            to=72,
            variable=self.main_size_var,
            command=lambda v: [
                self.main_size_label.configure(text=f"{int(v)}px"),
                self.on_browser_style_change("main", "font_size", int(v))
            ]
        )
        main_size_slider.grid(row=1, column=2, sticky="ew", padx=5, pady=2)

        self.main_color_label = ctk.CTkLabel(main_controls, text=self.lang.get("browser_output.text_color"))
        self.main_color_label.grid(row=2, column=0, sticky="w", padx=5, pady=2)

        self.main_color_var = ctk.StringVar(value=main_config.get("color", "#FFFFFF"))
        self.main_color_button = ctk.CTkButton(
            main_controls,
            text=self.main_color_var.get(),
            fg_color=self.main_color_var.get(),
            text_color=self._get_contrast_color(self.main_color_var.get()),
            command=lambda: self.pick_color("main", "color", self.main_color_var, self.main_color_button),
            width=120,
            height=30
        )
        self.main_color_button.grid(row=2, column=1, sticky="w", padx=5, pady=2)

        self.main_shadow_label = ctk.CTkLabel(main_controls, text=self.lang.get("browser_output.shadow_color"))
        self.main_shadow_label.grid(row=3, column=0, sticky="w", padx=5, pady=2)

        self.main_shadow_var = ctk.StringVar(value=main_config.get("shadow_color", "#000000"))
        self.main_shadow_button = ctk.CTkButton(
            main_controls,
            text=self.main_shadow_var.get(),
            fg_color=self.main_shadow_var.get(),
            text_color=self._get_contrast_color(self.main_shadow_var.get()),
            command=lambda: self.pick_color("main", "shadow_color", self.main_shadow_var, self.main_shadow_button),
            width=120,
            height=30
        )
        self.main_shadow_button.grid(row=3, column=1, sticky="w", padx=5, pady=2)

        # Background Opacity Slider
        ctk.CTkLabel(main_controls, text="BG Opacity:").grid(row=4, column=0, sticky="w", padx=5, pady=2)

        self.main_opacity_var = ctk.DoubleVar(value=main_config.get("bg_opacity", 0.7))
        self.main_opacity_label = ctk.CTkLabel(main_controls, text=f"{int(self.main_opacity_var.get() * 100)}%")
        self.main_opacity_label.grid(row=4, column=1, sticky="w", padx=5, pady=2)

        main_opacity_slider = ctk.CTkSlider(
            main_controls,
            from_=0,
            to=1,
            variable=self.main_opacity_var,
            command=lambda v: [
                self.main_opacity_label.configure(text=f"{int(float(v) * 100)}%"),
                self.on_browser_style_change("main", "bg_opacity", float(v))
            ]
        )
        main_opacity_slider.grid(row=4, column=2, sticky="ew", padx=5, pady=2)

        main_controls.columnconfigure(1, weight=1)
        main_controls.columnconfigure(2, weight=2)

        # Translation 1 Styling
        trans1_styling_frame = ctk.CTkFrame(browser_section)
        trans1_styling_frame.pack(fill="x", padx=5, pady=5)

        self.trans1_styling_label = ctk.CTkLabel(
            trans1_styling_frame,
            text=self.lang.get("browser_output.trans1_styling"),
            font=("Arial", 12, "bold")
        )
        self.trans1_styling_label.pack(anchor="w", padx=5, pady=3)

        trans1_config = self.config.config.get("browser_output", {}).get("trans1", {})

        trans1_controls = ctk.CTkFrame(trans1_styling_frame)
        trans1_controls.pack(fill="x", padx=10, pady=3)

        self.trans1_font_label = ctk.CTkLabel(trans1_controls, text=self.lang.get("browser_output.font"))
        self.trans1_font_label.grid(row=0, column=0, sticky="w", padx=5, pady=2)

        self.trans1_font_var = ctk.StringVar(value=trans1_config.get("font", "Arial"))
        trans1_font_menu = ctk.CTkOptionMenu(
            trans1_controls,
            variable=self.trans1_font_var,
            values=fonts,
            command=lambda v: self.on_browser_style_change("trans1", "font", v)
        )
        trans1_font_menu.grid(row=0, column=1, sticky="ew", padx=5, pady=2)

        # Font Size Slider
        ctk.CTkLabel(trans1_controls, text="Font Size:").grid(row=1, column=0, sticky="w", padx=5, pady=2)

        self.trans1_size_var = ctk.IntVar(value=trans1_config.get("font_size", 28))
        self.trans1_size_label = ctk.CTkLabel(trans1_controls, text=f"{self.trans1_size_var.get()}px")
        self.trans1_size_label.grid(row=1, column=1, sticky="w", padx=5, pady=2)

        trans1_size_slider = ctk.CTkSlider(
            trans1_controls,
            from_=16,
            to=72,
            variable=self.trans1_size_var,
            command=lambda v: [
                self.trans1_size_label.configure(text=f"{int(v)}px"),
                self.on_browser_style_change("trans1", "font_size", int(v))
            ]
        )
        trans1_size_slider.grid(row=1, column=2, sticky="ew", padx=5, pady=2)

        self.trans1_color_label = ctk.CTkLabel(trans1_controls, text=self.lang.get("browser_output.text_color"))
        self.trans1_color_label.grid(row=2, column=0, sticky="w", padx=5, pady=2)

        self.trans1_color_var = ctk.StringVar(value=trans1_config.get("color", "#FFFF00"))
        self.trans1_color_button = ctk.CTkButton(
            trans1_controls,
            text=self.trans1_color_var.get(),
            fg_color=self.trans1_color_var.get(),
            text_color=self._get_contrast_color(self.trans1_color_var.get()),
            command=lambda: self.pick_color("trans1", "color", self.trans1_color_var, self.trans1_color_button),
            width=120,
            height=30
        )
        self.trans1_color_button.grid(row=2, column=1, sticky="w", padx=5, pady=2)

        self.trans1_shadow_label = ctk.CTkLabel(trans1_controls, text=self.lang.get("browser_output.shadow_color"))
        self.trans1_shadow_label.grid(row=3, column=0, sticky="w", padx=5, pady=2)

        self.trans1_shadow_var = ctk.StringVar(value=trans1_config.get("shadow_color", "#000000"))
        self.trans1_shadow_button = ctk.CTkButton(
            trans1_controls,
            text=self.trans1_shadow_var.get(),
            fg_color=self.trans1_shadow_var.get(),
            text_color=self._get_contrast_color(self.trans1_shadow_var.get()),
            command=lambda: self.pick_color("trans1", "shadow_color", self.trans1_shadow_var, self.trans1_shadow_button),
            width=120,
            height=30
        )
        self.trans1_shadow_button.grid(row=3, column=1, sticky="w", padx=5, pady=2)

        # Background Opacity Slider
        ctk.CTkLabel(trans1_controls, text="BG Opacity:").grid(row=4, column=0, sticky="w", padx=5, pady=2)

        self.trans1_opacity_var = ctk.DoubleVar(value=trans1_config.get("bg_opacity", 0.7))
        self.trans1_opacity_label = ctk.CTkLabel(trans1_controls, text=f"{int(self.trans1_opacity_var.get() * 100)}%")
        self.trans1_opacity_label.grid(row=4, column=1, sticky="w", padx=5, pady=2)

        trans1_opacity_slider = ctk.CTkSlider(
            trans1_controls,
            from_=0,
            to=1,
            variable=self.trans1_opacity_var,
            command=lambda v: [
                self.trans1_opacity_label.configure(text=f"{int(float(v) * 100)}%"),
                self.on_browser_style_change("trans1", "bg_opacity", float(v))
            ]
        )
        trans1_opacity_slider.grid(row=4, column=2, sticky="ew", padx=5, pady=2)

        trans1_controls.columnconfigure(1, weight=1)
        trans1_controls.columnconfigure(2, weight=2)

        # Translation 2 Styling
        trans2_styling_frame = ctk.CTkFrame(browser_section)
        trans2_styling_frame.pack(fill="x", padx=5, pady=5)

        self.trans2_styling_label = ctk.CTkLabel(
            trans2_styling_frame,
            text=self.lang.get("browser_output.trans2_styling"),
            font=("Arial", 12, "bold")
        )
        self.trans2_styling_label.pack(anchor="w", padx=5, pady=3)

        trans2_config = self.config.config.get("browser_output", {}).get("trans2", {})

        trans2_controls = ctk.CTkFrame(trans2_styling_frame)
        trans2_controls.pack(fill="x", padx=10, pady=3)

        self.trans2_font_label = ctk.CTkLabel(trans2_controls, text=self.lang.get("browser_output.font"))
        self.trans2_font_label.grid(row=0, column=0, sticky="w", padx=5, pady=2)

        self.trans2_font_var = ctk.StringVar(value=trans2_config.get("font", "Arial"))
        trans2_font_menu = ctk.CTkOptionMenu(
            trans2_controls,
            variable=self.trans2_font_var,
            values=fonts,
            command=lambda v: self.on_browser_style_change("trans2", "font", v)
        )
        trans2_font_menu.grid(row=0, column=1, sticky="ew", padx=5, pady=2)

        # Font Size Slider
        ctk.CTkLabel(trans2_controls, text="Font Size:").grid(row=1, column=0, sticky="w", padx=5, pady=2)

        self.trans2_size_var = ctk.IntVar(value=trans2_config.get("font_size", 28))
        self.trans2_size_label = ctk.CTkLabel(trans2_controls, text=f"{self.trans2_size_var.get()}px")
        self.trans2_size_label.grid(row=1, column=1, sticky="w", padx=5, pady=2)

        trans2_size_slider = ctk.CTkSlider(
            trans2_controls,
            from_=16,
            to=72,
            variable=self.trans2_size_var,
            command=lambda v: [
                self.trans2_size_label.configure(text=f"{int(v)}px"),
                self.on_browser_style_change("trans2", "font_size", int(v))
            ]
        )
        trans2_size_slider.grid(row=1, column=2, sticky="ew", padx=5, pady=2)

        self.trans2_color_label = ctk.CTkLabel(trans2_controls, text=self.lang.get("browser_output.text_color"))
        self.trans2_color_label.grid(row=2, column=0, sticky="w", padx=5, pady=2)

        self.trans2_color_var = ctk.StringVar(value=trans2_config.get("color", "#00FFFF"))
        self.trans2_color_button = ctk.CTkButton(
            trans2_controls,
            text=self.trans2_color_var.get(),
            fg_color=self.trans2_color_var.get(),
            text_color=self._get_contrast_color(self.trans2_color_var.get()),
            command=lambda: self.pick_color("trans2", "color", self.trans2_color_var, self.trans2_color_button),
            width=120,
            height=30
        )
        self.trans2_color_button.grid(row=2, column=1, sticky="w", padx=5, pady=2)

        self.trans2_shadow_label = ctk.CTkLabel(trans2_controls, text=self.lang.get("browser_output.shadow_color"))
        self.trans2_shadow_label.grid(row=3, column=0, sticky="w", padx=5, pady=2)

        self.trans2_shadow_var = ctk.StringVar(value=trans2_config.get("shadow_color", "#000000"))
        self.trans2_shadow_button = ctk.CTkButton(
            trans2_controls,
            text=self.trans2_shadow_var.get(),
            fg_color=self.trans2_shadow_var.get(),
            text_color=self._get_contrast_color(self.trans2_shadow_var.get()),
            command=lambda: self.pick_color("trans2", "shadow_color", self.trans2_shadow_var, self.trans2_shadow_button),
            width=120,
            height=30
        )
        self.trans2_shadow_button.grid(row=3, column=1, sticky="w", padx=5, pady=2)

        # Background Opacity Slider
        ctk.CTkLabel(trans2_controls, text="BG Opacity:").grid(row=4, column=0, sticky="w", padx=5, pady=2)

        self.trans2_opacity_var = ctk.DoubleVar(value=trans2_config.get("bg_opacity", 0.7))
        self.trans2_opacity_label = ctk.CTkLabel(trans2_controls, text=f"{int(self.trans2_opacity_var.get() * 100)}%")
        self.trans2_opacity_label.grid(row=4, column=1, sticky="w", padx=5, pady=2)

        trans2_opacity_slider = ctk.CTkSlider(
            trans2_controls,
            from_=0,
            to=1,
            variable=self.trans2_opacity_var,
            command=lambda v: [
                self.trans2_opacity_label.configure(text=f"{int(float(v) * 100)}%"),
                self.on_browser_style_change("trans2", "bg_opacity", float(v))
            ]
        )
        trans2_opacity_slider.grid(row=4, column=2, sticky="ew", padx=5, pady=2)

        trans2_controls.columnconfigure(1, weight=1)
        trans2_controls.columnconfigure(2, weight=2)

        # Instructions
        instructions_frame = ctk.CTkFrame(browser_section)
        instructions_frame.pack(fill="x", padx=5, pady=5)

        self.instructions_text = ctk.CTkTextbox(
            instructions_frame,
            height=120,
            font=("Arial", 10),
            wrap="word"
        )
        self.instructions_text.pack(fill="x", padx=5, pady=5)
        self.instructions_text.insert("1.0", self.lang.get("browser_output.instructions"))
        self.instructions_text.configure(state="disabled")

    def create_monitor_panel(self, parent):
        """Create monitoring panel"""

        self.monitor_label = ctk.CTkLabel(parent, text=self.lang.get("audio_monitor"), font=("Arial", 18, "bold"))
        self.monitor_label.pack(pady=10)

        # Audio level meter
        self.audio_meter = AudioLevelMeter(parent, lang_manager=self.lang)
        self.audio_meter.pack(fill="x", padx=10, pady=10)

        # Status display
        status_frame = ctk.CTkFrame(parent)
        status_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.transcription_label = ctk.CTkLabel(status_frame, text=self.lang.get("latest_transcription"), font=("Arial", 14, "bold"))
        self.transcription_label.pack(pady=5)

        self.transcription_text = ctk.CTkTextbox(status_frame, height=200, font=("Arial", 12))
        self.transcription_text.pack(fill="both", expand=True, padx=5, pady=5)

        # Output file status
        self.output_label = ctk.CTkLabel(status_frame, text=self.lang.get("output_not_started"), font=("Arial", 10))
        self.output_label.pack(pady=5)

    def create_control_panel(self, parent):
        """Create control buttons"""

        # Start/Stop button
        self.start_button = ctk.CTkButton(
            parent,
            text=self.lang.get("buttons.start"),
            command=self.toggle_recognition,
            height=50,
            font=("Arial", 16, "bold"),
            fg_color="#00aa00",
            hover_color="#00dd00"
        )
        self.start_button.pack(side="left", fill="x", expand=True, padx=5)

        # Setup Wizard button
        self.wizard_button = ctk.CTkButton(
            parent,
            text=self.lang.get("buttons.wizard"),
            command=self.open_wizard,
            height=50,
            font=("Arial", 16),
            fg_color="#4444aa",
            hover_color="#6666cc"
        )
        self.wizard_button.pack(side="right", padx=5)

        # Open Models Folder button
        self.models_button = ctk.CTkButton(
            parent,
            text=self.lang.get("buttons.models_folder"),
            command=self.open_models_folder,
            height=50,
            font=("Arial", 16),
            fg_color="#aa6600",
            hover_color="#cc8800"
        )
        self.models_button.pack(side="right", padx=5)

    def update_threshold_label(self, label, value):
        """Update threshold label when slider moves"""
        label.configure(text=self.lang.get("threshold_value", value=int(value)))
        if hasattr(self, 'audio_meter'):
            self.audio_meter.gate_threshold = int(value)

        # Save to config immediately
        self.config.config["audio"]["gate_threshold_db"] = int(value)
        self.config.save_config(self.config.config)

    def update_release_label(self, label, value):
        """Update release time label when slider moves"""
        label.configure(text=self.lang.get("release_time_value", value=value))

        # Save to config immediately
        self.config.config["audio"]["gate_release_time"] = float(value)
        self.config.save_config(self.config.config)

    def on_device_change(self, device_str):
        """Handle device selection change"""
        if device_str == "No devices":
            device_id = None
        else:
            device_id = int(device_str.split(":")[0])

        # Save to config immediately
        self.config.config["audio"]["device"] = device_id
        self.config.save_config(self.config.config)
        print(f"Selected and saved device: {device_id}")

    def on_model_change(self, model_size):
        """Handle model selection change"""
        # Save to config immediately
        self.config.config["whisper"]["model_size"] = model_size
        self.config.save_config(self.config.config)
        print(f"Selected and saved model: {model_size}")

    def on_recog_language_change(self, language):
        """Handle recognition language change"""
        # Save to config immediately (convert 'auto' to None)
        lang_value = None if language == "auto" else language
        self.config.config["whisper"]["language"] = lang_value
        self.config.save_config(self.config.config)
        print(f"Selected and saved recognition language: {language}")

    def on_trans1_change(self, language):
        """Handle translation language 1 change"""
        # Save to config immediately (convert 'none' to None)
        lang_value = None if language == "none" else language
        if "translation" not in self.config.config:
            self.config.config["translation"] = {}
        self.config.config["translation"]["target_language_1"] = lang_value
        self.config.save_config(self.config.config)
        print(f"Selected and saved translation language 1: {language}")

    def on_trans2_change(self, language):
        """Handle translation language 2 change"""
        # Save to config immediately (convert 'none' to None)
        lang_value = None if language == "none" else language
        if "translation" not in self.config.config:
            self.config.config["translation"] = {}
        self.config.config["translation"]["target_language_2"] = lang_value
        self.config.save_config(self.config.config)
        print(f"Selected and saved translation language 2: {language}")

    def on_output_setting_change(self):
        """Handle output setting checkbox changes"""
        # Save to config immediately
        if "output" not in self.config.config:
            self.config.config["output"] = {}
        self.config.config["output"]["show_main"] = self.output_main_var.get()
        self.config.config["output"]["show_translation_1"] = self.output_trans1_var.get()
        self.config.config["output"]["show_translation_2"] = self.output_trans2_var.get()
        self.config.save_config(self.config.config)
        print(f"Output settings: Main={self.output_main_var.get()}, Trans1={self.output_trans1_var.get()}, Trans2={self.output_trans2_var.get()}")

    def on_output_method_change(self, method):
        """Handle output method change"""
        # Save to config immediately
        if "output" not in self.config.config:
            self.config.config["output"] = {}
        self.config.config["output"]["method"] = method
        self.config.save_config(self.config.config)
        print(f"Output method: {method}")

    def copy_url_to_clipboard(self):
        """Copy browser URL to clipboard"""
        self.clipboard_clear()
        self.clipboard_append(self.browser_url)
        self.update()  # Required for clipboard to work

        # Show feedback
        original_text = self.copy_url_button.cget("text")
        self.copy_url_button.configure(text=self.lang.get("browser_output.url_copied"))
        self.after(2000, lambda: self.copy_url_button.configure(text=original_text))

    def on_browser_style_change(self, target, property_name, value):
        """Handle browser style change"""
        # Ensure browser_output section exists
        if "browser_output" not in self.config.config:
            self.config.config["browser_output"] = {}

        # Ensure target section exists
        if target not in self.config.config["browser_output"]:
            self.config.config["browser_output"][target] = {}

        # Update config
        self.config.config["browser_output"][target][property_name] = value
        self.config.save_config(self.config.config)
        print(f"Browser style updated: {target}.{property_name} = {value}")

    def pick_color(self, target, property_name, color_var, button):
        """Open color picker dialog"""
        # Get current color
        current_color = color_var.get()

        # Open color picker
        color = colorchooser.askcolor(
            color=current_color,
            title="Choose Color"
        )

        # color is a tuple: ((r, g, b), '#rrggbb')
        if color[1]:  # If user selected a color (not cancelled)
            hex_color = color[1].upper()

            # Update variable
            color_var.set(hex_color)

            # Update button appearance
            button.configure(
                text=hex_color,
                fg_color=hex_color,
                text_color=self._get_contrast_color(hex_color)
            )

            # Save to config
            self.on_browser_style_change(target, property_name, hex_color)

    def _get_contrast_color(self, hex_color):
        """Get contrasting text color (black or white) for a background color"""
        try:
            # Remove '#' if present
            hex_color = hex_color.lstrip('#')

            # Convert to RGB
            r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

            # Calculate luminance
            luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255

            # Return black for light backgrounds, white for dark backgrounds
            return '#000000' if luminance > 0.5 else '#FFFFFF'
        except:
            return '#FFFFFF'  # Default to white if parsing fails

    def start_browser_server(self):
        """Start Flask server for browser output"""
        port = self.config.config.get("browser_output", {}).get("port", 8765)

        def run_server():
            try:
                print(f"Starting browser output server on http://127.0.0.1:{port}")
                browser_server.run_server(port=port)
            except Exception as e:
                print(f"Error starting browser server: {e}")

        self.browser_server_thread = threading.Thread(target=run_server, daemon=True)
        self.browser_server_thread.start()

    def toggle_recognition(self):
        """Start or stop speech recognition"""
        if not self.is_running:
            self.start_recognition()
        else:
            self.stop_recognition()

    def start_recognition(self):
        """Start speech recognition"""
        # Update config with UI values
        device_str = self.device_var.get()
        device_id = int(device_str.split(":")[0]) if device_str != "No devices" else None

        self.config.config["audio"]["device"] = device_id
        self.config.config["audio"]["gate_threshold_db"] = self.threshold_var.get()
        self.config.config["audio"]["gate_release_time"] = self.release_var.get()
        self.config.config["whisper"]["model_size"] = self.model_var.get()

        lang = self.lang_var.get()
        self.config.config["whisper"]["language"] = None if lang == "auto" else lang

        # Show loading dialog
        model_size = self.model_var.get()
        loading = LoadingDialog(
            self,
            title="Loading Whisper Model",
            message=f"Loading {model_size} model..."
        )
        loading.update_status("This may take a few minutes on first run")

        # Load model in background thread
        def load_model():
            try:
                loading.update_status("Downloading/loading model files...")

                # Initialize components
                self.audio_capture = AudioCapture(self.config)

                # Start monitoring download progress in another thread
                import os
                cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
                model_cache_pattern = f"models--Systran--faster-whisper-{model_size}"

                def monitor_download():
                    """Monitor download by checking file sizes"""
                    last_size = 0
                    no_change_count = 0
                    initial_time = time.time()

                    while self.recognizer is None:
                        try:
                            # Find model directory
                            model_dirs = list(cache_dir.glob(f"{model_cache_pattern}*"))
                            if model_dirs:
                                model_dir = model_dirs[0]

                                # Get total size of downloading files
                                total_size = 0
                                for file in model_dir.rglob("*"):
                                    if file.is_file():
                                        total_size += file.stat().st_size

                                # Check if size stopped changing (download complete)
                                if total_size == last_size:
                                    no_change_count += 1
                                else:
                                    no_change_count = 0

                                # If size hasn't changed for 3 checks, download is done
                                if no_change_count >= 3:
                                    size_mb = total_size / (1024 * 1024)
                                    loading.after(0, lambda s=size_mb: loading.update_status(
                                        f"Downloaded {s:.1f} MB - Loading into memory..."
                                    ))
                                    break  # Stop monitoring

                                # Calculate speed (average over total time)
                                now = time.time()
                                elapsed_total = now - initial_time

                                if elapsed_total > 1 and total_size > last_size:
                                    # Average speed since start
                                    avg_speed = total_size / elapsed_total

                                    # Update loading dialog
                                    size_mb = total_size / (1024 * 1024)
                                    if avg_speed > 1024 * 1024:
                                        speed_str = f"{avg_speed / (1024 * 1024):.1f} MB/s"
                                    else:
                                        speed_str = f"{avg_speed / 1024:.1f} KB/s"

                                    loading.after(0, lambda s=size_mb, sp=speed_str: loading.update_status(
                                        f"Downloading: {s:.1f} MB • {sp}"
                                    ))

                                last_size = total_size
                        except Exception as e:
                            pass

                        time.sleep(1.0)  # Check every second

                monitor_thread = threading.Thread(target=monitor_download, daemon=True)
                monitor_thread.start()

                self.recognizer = SpeechRecognizer(self.config)

                loading.update_status("Starting audio capture...")

                # Start audio capture
                self.audio_capture.start()

                # Start monitoring thread
                self.is_running = True
                self.stop_monitoring.clear()
                self.monitor_thread = threading.Thread(target=self.monitoring_loop, daemon=True)
                self.monitor_thread.start()

                # Update UI (must use after() for thread safety)
                self.after(0, lambda: self.start_button.configure(
                    text=self.lang.get("buttons.stop"),
                    fg_color="#aa0000",
                    hover_color="#dd0000"
                ))
                self.after(0, lambda: self.output_label.configure(text=self.lang.get("output_updating")))

                loading.update_status("Ready!")
                print("Speech recognition started")

                # Close loading dialog
                self.after(0, loading.close)

            except Exception as e:
                # Print full traceback for debugging
                error_msg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
                print(f"Error starting recognition:\n{error_msg}")

                # Show error in transcription area
                self.after(0, lambda: self.transcription_text.insert("1.0", f"❌ Error: {str(e)}\n"))

                # Close loading dialog
                self.after(0, loading.close)

                # Show error dialog with helpful message
                error_title = "Model Loading Failed"
                error_text = f"Failed to load {model_size} model:\n\n{str(e)}\n\n"

                # Check if it's a download-related error
                if "download" in str(e).lower() or "xet_get" in error_msg or "snapshot_download" in error_msg:
                    error_text += "This might be a corrupted download or network issue.\n\n"
                    error_text += "Try:\n"
                    error_text += "1. Check your internet connection\n"
                    error_text += "2. Try a smaller model (base or small)\n"
                    error_text += "3. Clear cache and retry (see console for cache location)"

                self.after(0, lambda: messagebox.showerror(error_title, error_text))

        # Start loading thread
        threading.Thread(target=load_model, daemon=True).start()

    def stop_recognition(self):
        """Stop speech recognition"""
        self.is_running = False
        self.stop_monitoring.set()

        if self.audio_capture:
            self.audio_capture.stop()

        # Update UI
        self.start_button.configure(
            text=self.lang.get("buttons.start"),
            fg_color="#00aa00",
            hover_color="#00dd00"
        )
        self.output_label.configure(text=self.lang.get("output_stopped"))

        print(self.lang.get("messages.stopped"))

    def monitoring_loop(self):
        """Background thread for audio monitoring and recognition"""
        output_file = Path("subtitles.txt")

        while not self.stop_monitoring.is_set():
            try:
                # Get audio chunk
                audio = self.audio_capture.get_audio_chunk()

                # Update audio meter
                if hasattr(self.audio_capture, 'gate_is_open'):
                    # Get current audio level for display
                    if self.audio_capture.audio_buffer:
                        import numpy as np
                        recent = np.concatenate(self.audio_capture.audio_buffer[-5:], axis=0) if len(self.audio_capture.audio_buffer) >= 5 else np.concatenate(self.audio_capture.audio_buffer, axis=0)
                        rms = np.sqrt(np.mean(recent ** 2))
                        db = self.audio_capture.rms_to_db(rms)
                    else:
                        db = -100

                    # Update meter in UI thread
                    self.after(0, lambda: self.audio_meter.update_level(db, self.audio_capture.gate_is_open))

                # Process audio if available
                if audio is not None:
                    main_text = self.recognizer.transcribe(audio, self.config["audio"]["sample_rate"])

                    if main_text:
                        # Get translation settings
                        source_lang = self.config.config.get("whisper", {}).get("language") or "auto"
                        target_lang_1 = self.config.config.get("translation", {}).get("target_language_1")
                        target_lang_2 = self.config.config.get("translation", {}).get("target_language_2")

                        # Translate if needed
                        trans1_text = None
                        trans2_text = None

                        if target_lang_1 and target_lang_1 != "none":
                            trans1_text = self.translator.translate(main_text, source_lang, target_lang_1)

                        if target_lang_2 and target_lang_2 != "none":
                            trans2_text = self.translator.translate(main_text, source_lang, target_lang_2)

                        # Build display text (show all in GUI)
                        display_parts = []
                        display_parts.append(f"[Main] {main_text}")
                        if trans1_text:
                            display_parts.append(f"[Trans1] {trans1_text}")
                        if trans2_text:
                            display_parts.append(f"[Trans2] {trans2_text}")
                        display_text = "\n".join(display_parts)

                        # Update GUI (show all)
                        self.after(0, lambda t=display_text: self.update_transcription(t))

                        # Build output text (only selected languages with prefixes for browser)
                        output_config = self.config.config.get("output", {})
                        output_parts = []

                        if output_config.get("show_main", True):
                            output_parts.append(f"[Main] {main_text}")
                        if output_config.get("show_translation_1", False) and trans1_text:
                            output_parts.append(f"[Trans1] {trans1_text}")
                        if output_config.get("show_translation_2", False) and trans2_text:
                            output_parts.append(f"[Trans2] {trans2_text}")

                        output_text = "\n".join(output_parts) if output_parts else f"[Main] {main_text}"

                        # Output based on method
                        output_method = output_config.get("method", "browser")
                        if output_method in ["file", "browser"]:
                            # Write to file for OBS/Browser
                            with open(output_file, 'w', encoding='utf-8') as f:
                                f.write(output_text)
                        elif output_method == "webhook":
                            # TODO: Send via WebSocket (placeholder for now)
                            print(f"[WebSocket] {output_text}")

                time.sleep(0.05)  # Small delay

            except Exception as e:
                print(f"Error in monitoring loop: {e}")
                time.sleep(0.1)

    def update_transcription(self, text: str):
        """Update transcription display"""
        self.transcription_text.delete("1.0", "end")
        self.transcription_text.insert("1.0", text)

    def open_wizard(self):
        """Open setup wizard"""
        wizard = SetupWizard(self, lang_manager=self.lang, on_complete=self.apply_wizard_settings)

    def open_models_folder(self):
        """Open the local models folder in file explorer"""
        import subprocess
        import os

        models_dir = Path(__file__).parent / "models"
        models_dir.mkdir(exist_ok=True)  # Create if doesn't exist

        # Open folder in file explorer (OS-specific)
        if os.name == 'nt':  # Windows
            subprocess.run(['explorer', str(models_dir)])
        elif os.name == 'posix':  # Linux/Mac
            subprocess.run(['xdg-open', str(models_dir)])

        print(f"\nOpened models folder: {models_dir}")
        print("See README.md in that folder for instructions on adding models manually.")

    def show_first_launch_language_dialog(self):
        """Show language selection dialog on first launch"""
        # Show language selection dialog
        dialog = LanguageSelectionDialog(self)
        selected_language = dialog.get_language()

        # Save language to config
        if "gui" not in self.config.config:
            self.config.config["gui"] = {}
        self.config.config["gui"]["language"] = selected_language
        self.config.config["gui"]["first_launch"] = False
        self.config.save_config(self.config.config)

        # Switch to selected language if different from default
        if selected_language != "en":
            self.switch_language(selected_language)

    def show_language_menu(self):
        """Show language selection menu"""
        # Create popup menu
        menu = ctk.CTkToplevel(self)
        menu.title("Select Language")
        menu.geometry("300x250")
        menu.resizable(False, False)

        # Make modal
        menu.transient(self)
        menu.grab_set()

        # Center on parent
        menu.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 300) // 2
        y = self.winfo_y() + (self.winfo_height() - 250) // 2
        menu.geometry(f"+{x}+{y}")

        # Title
        title = ctk.CTkLabel(menu, text="Select Language", font=("Arial", 16, "bold"))
        title.pack(pady=20)

        # Language buttons
        for lang_code, lang_name in self.lang.get_available_languages().items():
            btn = ctk.CTkButton(
                menu,
                text=f"{lang_name}",
                font=("Arial", 14),
                height=50,
                command=lambda lc=lang_code: self.switch_language(lc, menu)
            )
            btn.pack(fill="x", padx=30, pady=5)

    def switch_language(self, language_code: str, menu_window=None):
        """Switch to a different language"""
        # Close menu if provided
        if menu_window:
            menu_window.destroy()

        # Switch language
        self.lang.switch_language(language_code)

        # Save to config
        if "gui" not in self.config.config:
            self.config.config["gui"] = {}
        self.config.config["gui"]["language"] = language_code
        self.config.save_config(self.config.config)

        # Update all UI text
        self.update_ui_language()

    def update_ui_language(self):
        """Update all UI text after language change"""
        # Update window title
        self.title(self.lang.get("app_title"))

        # Update top bar
        self.title_label.configure(text=self.lang.get("app_header"))
        self.lang_button.configure(text=self.lang.get("buttons.language") + f" {self.lang.get_language_name()}")

        # Update buttons
        if self.is_running:
            self.start_button.configure(text=self.lang.get("buttons.stop"))
        else:
            self.start_button.configure(text=self.lang.get("buttons.start"))

        self.wizard_button.configure(text=self.lang.get("buttons.wizard"))
        self.models_button.configure(text=self.lang.get("buttons.models_folder"))

        # Update settings panel header
        self.settings_header.configure(text=self.lang.get("settings"))

        # Update settings panel labels
        self.audio_device_label.configure(text=self.lang.get("audio_device"))
        self.noise_gate_label.configure(text=self.lang.get("noise_gate"))
        self.threshold_label.configure(text=self.lang.get("threshold_value", value=self.threshold_var.get()))
        self.release_label.configure(text=self.lang.get("release_time_value", value=self.release_var.get()))
        self.model_label.configure(text=self.lang.get("model_settings"))

        # Update languages section
        self.languages_header_label.configure(text=self.lang.get("languages_section"))
        self.main_language_label.configure(text=self.lang.get("main_language"))
        self.trans1_label.configure(text=self.lang.get("translated_language_1"))
        self.trans2_label.configure(text=self.lang.get("translated_language_2"))

        # Update output settings
        self.output_settings_label.configure(text=self.lang.get("output_settings"))
        self.output_main_checkbox.configure(text=self.lang.get("output_main"))
        self.output_trans1_checkbox.configure(text=self.lang.get("output_trans1"))
        self.output_trans2_checkbox.configure(text=self.lang.get("output_trans2"))
        self.output_method_label.configure(text=self.lang.get("output_method"))
        self.output_note_label.configure(text=self.lang.get("output_note"))

        # Update browser output settings
        self.browser_output_label.configure(text=self.lang.get("browser_output.title"))
        self.url_label.configure(text=self.lang.get("browser_output.url_label"))
        self.copy_url_button.configure(text=self.lang.get("browser_output.copy_url"))
        self.main_styling_label.configure(text=self.lang.get("browser_output.main_styling"))
        self.main_font_label.configure(text=self.lang.get("browser_output.font"))
        self.main_color_label.configure(text=self.lang.get("browser_output.text_color"))
        self.main_shadow_label.configure(text=self.lang.get("browser_output.shadow_color"))
        self.trans1_styling_label.configure(text=self.lang.get("browser_output.trans1_styling"))
        self.trans1_font_label.configure(text=self.lang.get("browser_output.font"))
        self.trans1_color_label.configure(text=self.lang.get("browser_output.text_color"))
        self.trans1_shadow_label.configure(text=self.lang.get("browser_output.shadow_color"))
        self.trans2_styling_label.configure(text=self.lang.get("browser_output.trans2_styling"))
        self.trans2_font_label.configure(text=self.lang.get("browser_output.font"))
        self.trans2_color_label.configure(text=self.lang.get("browser_output.text_color"))
        self.trans2_shadow_label.configure(text=self.lang.get("browser_output.shadow_color"))
        self.instructions_text.configure(state="normal")
        self.instructions_text.delete("1.0", "end")
        self.instructions_text.insert("1.0", self.lang.get("browser_output.instructions"))
        self.instructions_text.configure(state="disabled")

        # Update monitor panel
        self.monitor_label.configure(text=self.lang.get("audio_monitor"))
        self.transcription_label.configure(text=self.lang.get("latest_transcription"))

        # Update output status based on current state
        if self.is_running:
            self.output_label.configure(text=self.lang.get("output_updating"))
        else:
            # Check if it was stopped or never started
            current_text = self.output_label.cget("text")
            if "Stopped" in current_text or "停止" in current_text or "Detenido" in current_text:
                self.output_label.configure(text=self.lang.get("output_stopped"))
            else:
                self.output_label.configure(text=self.lang.get("output_not_started"))

        print(f"Language switched to: {self.lang.get_language_name()}")

    def apply_wizard_settings(self, settings: Dict[str, Any]):
        """Apply settings from wizard"""
        if 'device' in settings:
            device_id = settings['device']
            devices = sd.query_devices()
            device_name = devices[device_id]['name']
            self.device_var.set(f"{device_id}: {device_name}")

        if 'gate_threshold_db' in settings:
            self.threshold_var.set(settings['gate_threshold_db'])

        if 'model_size' in settings:
            self.model_var.set(settings['model_size'])

        print(f"Applied wizard settings: {settings}")

    def on_closing(self):
        """Handle window close"""
        if self.is_running:
            self.stop_recognition()
        self.destroy()


def main():
    """Main entry point"""
    app = MainApplication()
    app.mainloop()


if __name__ == "__main__":
    main()
