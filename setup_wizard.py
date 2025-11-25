"""
jimakuChan Setup Wizard
OBS-style setup wizard for first-time configuration
"""

import customtkinter as ctk
import sounddevice as sd
import numpy as np
import threading
import time
from typing import Optional, Callable


class SetupWizard(ctk.CTkToplevel):
    """Setup wizard window"""

    def __init__(self, parent, lang_manager=None, on_complete: Optional[Callable] = None):
        super().__init__(parent)

        self.lang = lang_manager
        self.title(self.lang.get("wizard.title") if self.lang else "jimakuChan Setup Wizard")
        self.geometry("700x600")
        self.resizable(False, False)

        # Make modal
        self.transient(parent)
        self.grab_set()

        # State
        self.current_step = 0
        self.on_complete = on_complete
        self.selected_device = None
        self.recommended_threshold = -40
        self.recommended_release = 0.8

        # Audio monitoring
        self.monitoring = False
        self.audio_stream = None
        self.audio_levels = []

        # Create UI
        self.create_ui()
        self.show_step(0)

    def create_ui(self):
        """Create wizard UI"""

        # Progress indicator
        self.progress_frame = ctk.CTkFrame(self, height=60)
        self.progress_frame.pack(fill="x", padx=20, pady=10)
        self.progress_frame.pack_propagate(False)

        self.progress_label = ctk.CTkLabel(
            self.progress_frame,
            text=self.lang.get("wizard.step1_progress") if self.lang else "Step 1 of 4: Microphone Selection",
            font=("Arial", 16, "bold")
        )
        self.progress_label.pack(pady=15)

        # Content area (fixed height to leave room for buttons)
        self.content_frame = ctk.CTkFrame(self, height=420)
        self.content_frame.pack(fill="both", padx=20, pady=10)
        self.content_frame.pack_propagate(False)  # Don't let children resize frame

        # Navigation buttons (always at bottom)
        nav_frame = ctk.CTkFrame(self, height=60)
        nav_frame.pack(fill="x", padx=20, pady=10)
        nav_frame.pack_propagate(False)

        self.back_button = ctk.CTkButton(
            nav_frame,
            text=self.lang.get("wizard.back") if self.lang else "← Back",
            command=self.previous_step,
            width=100
        )
        self.back_button.pack(side="left", padx=5)

        self.next_button = ctk.CTkButton(
            nav_frame,
            text=self.lang.get("wizard.next") if self.lang else "Next →",
            command=self.next_step,
            width=100,
            fg_color="#00aa00",
            hover_color="#00dd00"
        )
        self.next_button.pack(side="right", padx=5)

        self.cancel_button = ctk.CTkButton(
            nav_frame,
            text=self.lang.get("wizard.cancel") if self.lang else "Cancel",
            command=self.cancel_wizard,
            width=100,
            fg_color="#aa0000",
            hover_color="#dd0000"
        )
        self.cancel_button.pack(side="right", padx=5)

    def clear_content(self):
        """Clear current content"""
        for widget in self.content_frame.winfo_children():
            widget.destroy()

    def show_step(self, step: int):
        """Show specific wizard step"""
        self.current_step = step
        self.clear_content()

        if step == 0:
            self.show_mic_selection()
        elif step == 1:
            self.show_noise_gate_calibration()
        elif step == 2:
            self.show_model_selection()
        elif step == 3:
            self.show_test_recognition()

        # Update navigation
        self.back_button.configure(state="disabled" if step == 0 else "normal")
        finish_text = self.lang.get("wizard.finish") if self.lang else "Finish"
        next_text = self.lang.get("wizard.next") if self.lang else "Next →"
        self.next_button.configure(text=finish_text if step == 3 else next_text)

    def show_mic_selection(self):
        """Step 1: Microphone selection"""
        self.progress_label.configure(text=self.lang.get("wizard.step1_progress") if self.lang else "Step 1 of 4: Microphone Selection")

        ctk.CTkLabel(
            self.content_frame,
            text=self.lang.get("wizard.step1_title") if self.lang else "🎤 Select Your Microphone",
            font=("Arial", 20, "bold")
        ).pack(pady=20)

        ctk.CTkLabel(
            self.content_frame,
            text=self.lang.get("wizard.step1_desc") if self.lang else "Choose the microphone you'll use for speech recognition:",
            font=("Arial", 12)
        ).pack(pady=10)

        # Get available devices
        devices = sd.query_devices()
        input_devices = [(i, d['name']) for i, d in enumerate(devices) if d['max_input_channels'] > 0]

        if not input_devices:
            ctk.CTkLabel(
                self.content_frame,
                text=self.lang.get("wizard.no_devices") if self.lang else "❌ No input devices found!",
                font=("Arial", 14),
                text_color="#ff0000"
            ).pack(pady=20)
            return

        # Device list
        device_frame = ctk.CTkScrollableFrame(self.content_frame, height=200)
        device_frame.pack(fill="x", padx=20, pady=10)

        self.device_var = ctk.IntVar(value=input_devices[0][0])

        for device_id, device_name in input_devices:
            radio = ctk.CTkRadioButton(
                device_frame,
                text=f"{device_name}",
                variable=self.device_var,
                value=device_id,
                font=("Arial", 12)
            )
            radio.pack(anchor="w", pady=5, padx=10)

        # Test button
        test_button = ctk.CTkButton(
            self.content_frame,
            text=self.lang.get("wizard.test_microphone") if self.lang else "🔊 Test Selected Microphone",
            command=self.test_microphone,
            height=40
        )
        test_button.pack(pady=10)

        self.test_result_label = ctk.CTkLabel(
            self.content_frame,
            text="",
            font=("Arial", 11)
        )
        self.test_result_label.pack()

    def show_noise_gate_calibration(self):
        """Step 2: Noise gate calibration"""
        self.progress_label.configure(
            text=self.lang.get("wizard.step2_progress") if self.lang else "Step 2 of 4: Noise Gate Calibration"
        )

        ctk.CTkLabel(
            self.content_frame,
            text=self.lang.get("wizard.step2_title") if self.lang else "🎚️ Calibrate Noise Gate",
            font=("Arial", 20, "bold")
        ).pack(pady=20)

        ctk.CTkLabel(
            self.content_frame,
            text=self.lang.get("wizard.step2_desc") if self.lang else "Speak the following sentence clearly:",
            font=("Arial", 12)
        ).pack(pady=10)

        # Test sentence
        sentence_frame = ctk.CTkFrame(self.content_frame)
        sentence_frame.pack(pady=10)

        test_sentence = self.lang.get("wizard.test_sentence") if self.lang else "The quick brown fox jumps over the lazy dog"
        ctk.CTkLabel(
            sentence_frame,
            text=f'"{test_sentence}"',
            font=("Arial", 14, "italic"),
            wraplength=500
        ).pack(padx=20, pady=15)

        # Audio meter
        self.calibration_canvas = ctk.CTkCanvas(
            self.content_frame,
            width=500,
            height=80,
            bg="#2b2b2b",
            highlightthickness=0
        )
        self.calibration_canvas.pack(pady=10)

        self.calibration_db_label = ctk.CTkLabel(
            self.content_frame,
            text=self.lang.get("wizard.current_level", level=-100) if self.lang else "Current Level: -100 dB",
            font=("Arial", 12)
        )
        self.calibration_db_label.pack()

        # Start/Stop monitoring
        self.monitor_button = ctk.CTkButton(
            self.content_frame,
            text=self.lang.get("wizard.start_monitoring") if self.lang else "▶️ Start Monitoring",
            command=self.toggle_monitoring,
            height=40,
            fg_color="#00aa00",
            hover_color="#00dd00"
        )
        self.monitor_button.pack(pady=15)

        # Threshold slider
        threshold_frame = ctk.CTkFrame(self.content_frame)
        threshold_frame.pack(fill="x", padx=40, pady=10)

        self.threshold_label = ctk.CTkLabel(
            threshold_frame,
            text=self.lang.get("wizard.gate_threshold", value=-40) if self.lang else "Gate Threshold: -40 dB",
            font=("Arial", 12)
        )
        self.threshold_label.pack(anchor="w")

        self.threshold_slider = ctk.CTkSlider(
            threshold_frame,
            from_=-60,
            to=-20,
            command=self.update_threshold_display
        )
        self.threshold_slider.set(-40)
        self.threshold_slider.pack(fill="x", pady=5)

        # Auto-calibrate button
        auto_button = ctk.CTkButton(
            self.content_frame,
            text=self.lang.get("wizard.auto_calibrate") if self.lang else "🔧 Auto-Calibrate",
            command=self.auto_calibrate
        )
        auto_button.pack()

    def show_model_selection(self):
        """Step 3: Model selection"""
        self.progress_label.configure(
            text=self.lang.get("wizard.step3_progress") if self.lang else "Step 3 of 4: Model Selection"
        )

        ctk.CTkLabel(
            self.content_frame,
            text=self.lang.get("wizard.step3_title") if self.lang else "🧠 Choose Whisper Model",
            font=("Arial", 20, "bold")
        ).pack(pady=20)

        ctk.CTkLabel(
            self.content_frame,
            text=self.lang.get("wizard.step3_desc") if self.lang else "Select the balance between accuracy and speed:",
            font=("Arial", 12)
        ).pack(pady=10)

        # Model options - get descriptions from language files
        model_names = ["tiny", "base", "small", "medium", "large"]

        self.model_var = ctk.StringVar(value="small")

        for model_name in model_names:
            frame = ctk.CTkFrame(self.content_frame)
            frame.pack(fill="x", padx=40, pady=5)

            radio = ctk.CTkRadioButton(
                frame,
                text="",
                variable=self.model_var,
                value=model_name
            )
            radio.pack(side="left", padx=10)

            info_frame = ctk.CTkFrame(frame)
            info_frame.pack(side="left", fill="x", expand=True)

            # Get model description from language files
            model_desc = self.lang.get(f"models.{model_name}") if self.lang else f"{model_name.title()} - No description"

            ctk.CTkLabel(
                info_frame,
                text=model_desc,
                font=("Arial", 11),
                text_color="#cccccc",
                wraplength=400,
                justify="left"
            ).pack(anchor="w", padx=5)

    def show_test_recognition(self):
        """Step 4: Test recognition"""
        self.progress_label.configure(
            text=self.lang.get("wizard.step4_progress") if self.lang else "Step 4 of 4: Test Recognition"
        )

        ctk.CTkLabel(
            self.content_frame,
            text=self.lang.get("wizard.step4_title") if self.lang else "✅ Test Your Setup",
            font=("Arial", 20, "bold")
        ).pack(pady=20)

        ctk.CTkLabel(
            self.content_frame,
            text=self.lang.get("wizard.step4_desc") if self.lang else "Your configuration is ready! Click 'Finish' to save and start.",
            font=("Arial", 12)
        ).pack(pady=10)

        # Summary
        summary_frame = ctk.CTkFrame(self.content_frame)
        summary_frame.pack(fill="both", expand=True, padx=40, pady=20)

        ctk.CTkLabel(
            summary_frame,
            text=self.lang.get("wizard.config_summary") if self.lang else "📋 Configuration Summary",
            font=("Arial", 16, "bold")
        ).pack(pady=10)

        # Summary details
        if hasattr(self, 'device_var'):
            device = sd.query_devices(self.device_var.get())
            ctk.CTkLabel(
                summary_frame,
                text=f"🎤 Microphone: {device['name']}",
                font=("Arial", 12)
            ).pack(anchor="w", padx=20, pady=5)

        if hasattr(self, 'threshold_slider'):
            ctk.CTkLabel(
                summary_frame,
                text=f"🎚️ Gate Threshold: {int(self.threshold_slider.get())} dB",
                font=("Arial", 12)
            ).pack(anchor="w", padx=20, pady=5)

        if hasattr(self, 'model_var'):
            ctk.CTkLabel(
                summary_frame,
                text=f"🧠 Model: {self.model_var.get().title()}",
                font=("Arial", 12)
            ).pack(anchor="w", padx=20, pady=5)

    def test_microphone(self):
        """Test selected microphone"""
        device_id = self.device_var.get()
        testing_text = self.lang.get("wizard.testing") if self.lang else "🔊 Testing microphone..."
        self.test_result_label.configure(text=testing_text, text_color="#ffaa00")

        def test():
            try:
                # Record brief audio
                duration = 1.0
                sample_rate = 16000
                recording = sd.rec(
                    int(duration * sample_rate),
                    samplerate=sample_rate,
                    channels=1,
                    device=device_id
                )
                sd.wait()

                # Check if we got audio
                rms = np.sqrt(np.mean(recording ** 2))
                if rms > 0.001:
                    working_text = self.lang.get("wizard.mic_working") if self.lang else "✅ Microphone working!"
                    self.after(0, lambda: self.test_result_label.configure(
                        text=working_text,
                        text_color="#00ff00"
                    ))
                else:
                    quiet_text = self.lang.get("wizard.mic_quiet") if self.lang else "⚠️ Very quiet or no input detected"
                    self.after(0, lambda: self.test_result_label.configure(
                        text=quiet_text,
                        text_color="#ffaa00"
                    ))

                self.selected_device = device_id

            except Exception as e:
                self.after(0, lambda: self.test_result_label.configure(
                    text=f"❌ Error: {e}",
                    text_color="#ff0000"
                ))

        threading.Thread(target=test, daemon=True).start()

    def toggle_monitoring(self):
        """Start/stop audio level monitoring"""
        if not self.monitoring:
            self.start_monitoring()
        else:
            self.stop_monitoring()

    def start_monitoring(self):
        """Start monitoring audio levels"""
        device_id = self.device_var.get() if hasattr(self, 'device_var') else None

        def callback(indata, frames, time_info, status):
            if status:
                print(status)

            # Calculate RMS and dB
            rms = np.sqrt(np.mean(indata ** 2))
            db = 20 * np.log10(rms) if rms > 1e-10 else -100

            self.audio_levels.append(db)
            if len(self.audio_levels) > 100:
                self.audio_levels.pop(0)

            # Update UI
            self.after(0, lambda: self.update_calibration_meter(db))

        try:
            self.audio_stream = sd.InputStream(
                device=device_id,
                channels=1,
                callback=callback,
                blocksize=1024,
                samplerate=16000
            )
            self.audio_stream.start()
            self.monitoring = True

            stop_text = self.lang.get("wizard.stop_monitoring") if self.lang else "⏹️ Stop Monitoring"
            self.monitor_button.configure(
                text=stop_text,
                fg_color="#aa0000",
                hover_color="#dd0000"
            )

        except Exception as e:
            print(f"Error starting monitoring: {e}")

    def stop_monitoring(self):
        """Stop monitoring"""
        if self.audio_stream:
            self.audio_stream.stop()
            self.audio_stream.close()
            self.audio_stream = None

        self.monitoring = False
        start_text = self.lang.get("wizard.start_monitoring") if self.lang else "▶️ Start Monitoring"
        self.monitor_button.configure(
            text=start_text,
            fg_color="#00aa00",
            hover_color="#00dd00"
        )

    def update_calibration_meter(self, db: float):
        """Update the calibration audio meter"""
        if not hasattr(self, 'calibration_canvas'):
            return

        level_text = self.lang.get("wizard.current_level", level=f"{db:.1f}") if self.lang else f"Current Level: {db:.1f} dB"
        self.calibration_db_label.configure(text=level_text)

        # Redraw meter
        canvas = self.calibration_canvas
        canvas.delete("all")

        # Background
        canvas.create_rectangle(10, 10, 490, 70, fill="#1a1a1a", outline="#444")

        # Level bar
        db_normalized = max(0, min(1, (db + 60) / 60))
        bar_width = int(470 * db_normalized)

        if db > -10:
            color = "#ff0000"
        elif db > -20:
            color = "#ffaa00"
        elif db > -40:
            color = "#00ff00"
        else:
            color = "#004400"

        if bar_width > 0:
            canvas.create_rectangle(10, 10, 10 + bar_width, 70, fill=color, outline="")

        # Threshold line
        if hasattr(self, 'threshold_slider'):
            threshold = self.threshold_slider.get()
            threshold_x = int(10 + 470 * ((threshold + 60) / 60))
            canvas.create_line(threshold_x, 10, threshold_x, 70, fill="#ffff00", width=3)
            canvas.create_text(threshold_x, 5, text=f"{int(threshold)}dB", fill="#ffff00", anchor="s")

    def update_threshold_display(self, value):
        """Update threshold label"""
        threshold_text = self.lang.get("wizard.gate_threshold", value=int(value)) if self.lang else f"Gate Threshold: {int(value)} dB"
        self.threshold_label.configure(text=threshold_text)

    def auto_calibrate(self):
        """Auto-calibrate based on recorded levels"""
        if not self.audio_levels:
            return

        # Find average speech level (excluding silence)
        speech_levels = [db for db in self.audio_levels if db > -50]

        if speech_levels:
            avg_speech = np.mean(speech_levels)
            # Set threshold 10dB below average speech
            recommended = max(-60, min(-20, avg_speech - 10))

            self.threshold_slider.set(recommended)
            self.update_threshold_display(recommended)

    def previous_step(self):
        """Go to previous step"""
        if self.current_step > 0:
            self.show_step(self.current_step - 1)

    def next_step(self):
        """Go to next step or finish"""
        if self.current_step < 3:
            self.show_step(self.current_step + 1)
        else:
            self.finish_wizard()

    def finish_wizard(self):
        """Complete wizard and save settings"""
        # Stop monitoring if active
        if self.monitoring:
            self.stop_monitoring()

        # Collect settings
        settings = {}

        if hasattr(self, 'device_var'):
            settings['device'] = self.device_var.get()

        if hasattr(self, 'threshold_slider'):
            settings['gate_threshold_db'] = int(self.threshold_slider.get())

        if hasattr(self, 'model_var'):
            settings['model_size'] = self.model_var.get()

        # Call completion callback
        if self.on_complete:
            self.on_complete(settings)

        self.destroy()

    def cancel_wizard(self):
        """Cancel wizard"""
        if self.monitoring:
            self.stop_monitoring()
        self.destroy()
