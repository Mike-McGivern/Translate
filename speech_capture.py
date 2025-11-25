"""
VanillaChanny Hardware Speech Capture
Desktop application for high-quality audio capture and speech recognition
Sends results to browser via WebSocket
"""

import asyncio
import json
import logging
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any

import numpy as np
import sounddevice as sd
import websockets
from faster_whisper import WhisperModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Config:
    """Configuration manager"""

    DEFAULT_CONFIG = {
        "audio": {
            "sample_rate": 16000,
            "channels": 1,
            "chunk_duration": 30,  # seconds
            "device": None,  # None = default device
            "noise_threshold": 0.01  # RMS threshold for silence detection
        },
        "whisper": {
            "model_size": "base",  # tiny, base, small, medium, large
            "device": "auto",  # auto, cpu, cuda
            "compute_type": "float16",  # float16, int8, int8_float16
            "language": "ja",  # Language code or None for auto-detect
            "beam_size": 5,
            "vad_filter": True  # Voice activity detection
        },
        "translation": {
            "target_language_1": None,  # First translation target (None = disabled)
            "target_language_2": None,  # Second translation target (None = disabled)
            "api_key": None  # Google Translate API key (or use free endpoint)
        },
        "output": {
            "show_main": True,  # Output main language
            "show_translation_1": False,  # Output translation 1
            "show_translation_2": False,  # Output translation 2
            "method": "file"  # "file" for browser source, "webhook" for WebSocket
        },
        "websocket": {
            "host": "localhost",
            "port": 8765
        },
        "gui": {
            "language": None,  # None = show selection dialog, or "en", "es", "ja"
            "first_launch": True  # Show language selection on first launch
        },
        "browser_output": {
            "port": 8765,  # Port for browser server
            "main": {
                "font": "Arial",
                "font_size": 32,
                "color": "#FFFFFF",
                "shadow_color": "#000000",
                "bg_opacity": 0.7
            },
            "trans1": {
                "font": "Arial",
                "font_size": 28,
                "color": "#FFFF00",
                "shadow_color": "#000000",
                "bg_opacity": 0.7
            },
            "trans2": {
                "font": "Arial",
                "font_size": 28,
                "color": "#00FFFF",
                "shadow_color": "#000000",
                "bg_opacity": 0.7
            }
        }
    }

    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file or create default"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                # Merge with defaults
                config = self.DEFAULT_CONFIG.copy()
                for key in config:
                    if key in loaded_config:
                        config[key].update(loaded_config[key])
                logger.info(f"Loaded configuration from {self.config_path}")
                return config
            except Exception as e:
                logger.error(f"Failed to load config: {e}")
                return self.DEFAULT_CONFIG.copy()
        else:
            # Create default config file
            self.save_config(self.DEFAULT_CONFIG)
            return self.DEFAULT_CONFIG.copy()

    def save_config(self, config: Dict[str, Any]):
        """Save configuration to file"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved configuration to {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def __getitem__(self, key):
        return self.config[key]


class AudioCapture:
    """Real-time audio capture with silence detection"""

    def __init__(self, config: Config):
        self.config = config
        self.audio_queue = queue.Queue()
        self.is_running = False
        self.stream = None

        # Audio settings
        self.sample_rate = config["audio"]["sample_rate"]
        self.channels = config["audio"]["channels"]
        self.device = config["audio"]["device"]

        # Buffer for accumulating audio
        self.audio_buffer = []
        self.buffer_duration = config["audio"]["chunk_duration"]
        self.max_buffer_samples = self.sample_rate * self.buffer_duration

        # Noise gate settings (like audio software)
        self.gate_threshold_db = config["audio"].get("gate_threshold_db", -40)
        self.gate_release_time = config["audio"].get("gate_release_time", 0.8)
        self.gate_is_open = False
        self.silence_timer = 0.0

        logger.info(f"Audio capture initialized: {self.sample_rate}Hz, {self.channels} channel(s)")
        logger.info(f"Noise gate: threshold={self.gate_threshold_db}dB, release={self.gate_release_time}s")

    def audio_callback(self, indata, frames, time_info, status):
        """Callback for audio stream"""
        if status:
            logger.warning(f"Audio callback status: {status}")

        # Copy audio data and add to queue
        audio_chunk = indata.copy()
        self.audio_queue.put(audio_chunk)

    def start(self):
        """Start audio capture"""
        if self.is_running:
            logger.warning("Audio capture already running")
            return

        try:
            self.is_running = True
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                device=self.device,
                callback=self.audio_callback,
                blocksize=1024
            )
            self.stream.start()
            logger.info("Audio capture started")
        except Exception as e:
            logger.error(f"Failed to start audio capture: {e}")
            self.is_running = False
            raise

    def stop(self):
        """Stop audio capture"""
        if not self.is_running:
            return

        self.is_running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        logger.info("Audio capture stopped")

    def rms_to_db(self, rms: float) -> float:
        """Convert RMS to decibels"""
        if rms < 1e-10:  # Avoid log(0)
            return -100
        return 20 * np.log10(rms)

    def get_audio_chunk(self) -> Optional[np.ndarray]:
        """Get accumulated audio chunk using noise gate logic"""
        if not self.is_running:
            return None

        # Collect audio from queue
        recent_chunks = []
        while not self.audio_queue.empty():
            chunk = self.audio_queue.get()
            self.audio_buffer.append(chunk)
            recent_chunks.append(chunk)

        # Need recent audio to analyze
        if not recent_chunks:
            return None

        # Analyze recent audio level
        recent_audio = np.concatenate(recent_chunks, axis=0)
        recent_rms = np.sqrt(np.mean(recent_audio ** 2))
        recent_db = self.rms_to_db(recent_rms)
        chunk_duration = len(recent_audio) / self.sample_rate

        # Noise gate logic
        if recent_db > self.gate_threshold_db:
            # Signal above threshold - open gate
            if not self.gate_is_open:
                logger.debug(f"🎤 Gate OPEN ({recent_db:.1f}dB)")
            self.gate_is_open = True
            self.silence_timer = 0.0
        else:
            # Signal below threshold
            if self.gate_is_open:
                # Gate is open but signal is quiet - start release timer
                self.silence_timer += chunk_duration

        # Check if we should process
        should_process = False

        # Concatenate all buffered audio
        if len(self.audio_buffer) == 0:
            return None

        audio = np.concatenate(self.audio_buffer, axis=0)
        total_samples = len(audio)

        # 1. Safety limit: hit maximum buffer
        if total_samples >= self.max_buffer_samples:
            should_process = True
            logger.debug(f"⚠️  Processing: hit max buffer ({self.buffer_duration}s)")

        # 2. Gate closed after being open (release time exceeded)
        elif self.gate_is_open and self.silence_timer >= self.gate_release_time:
            # Only process if we have meaningful audio (at least 0.5 seconds)
            if total_samples >= self.sample_rate * 0.5:
                should_process = True
                logger.debug(f"🔇 Gate CLOSED - Processing {total_samples / self.sample_rate:.1f}s of audio")

        if should_process:
            # Process and reset
            self.audio_buffer = []
            self.gate_is_open = False
            self.silence_timer = 0.0
            return audio.flatten()

        return None


class SpeechRecognizer:
    """Speech recognition using faster-whisper"""

    def __init__(self, config: Config, download_progress_class=None):
        self.config = config

        # Whisper settings
        model_size = config["whisper"]["model_size"]
        device = config["whisper"]["device"]
        compute_type = config["whisper"]["compute_type"]

        # Force CPU mode if device is auto (to avoid CUDA issues)
        if device == "auto":
            device = "cpu"
            compute_type = "int8"
            logger.info("Auto-detection: Using CPU mode")

        # Check for local model first
        local_models_dir = Path(__file__).parent / "models"
        local_model_path = local_models_dir / model_size

        if local_model_path.exists() and (local_model_path / "config.json").exists():
            model_to_load = str(local_model_path)
            logger.info(f"Found local model at: {local_model_path}")
            logger.info(f"Loading Whisper model from local path (device: {device}, compute: {compute_type})")
        else:
            model_to_load = model_size
            logger.info(f"Loading Whisper model: {model_size} from HuggingFace (device: {device}, compute: {compute_type})")

        try:
            # Prepare model kwargs
            model_kwargs = {
                "device": device,
                "compute_type": compute_type
            }

            # Add custom progress class if provided (only for HF downloads)
            if download_progress_class and model_to_load == model_size:
                import os
                os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '0'  # Enable progress bars
                model_kwargs["download_kwargs"] = {"tqdm_class": download_progress_class}

            self.model = WhisperModel(model_to_load, **model_kwargs)
            logger.info("Whisper model loaded successfully")
        except Exception as e:
            # If CUDA/GPU fails, try CPU fallback
            if device != "cpu":
                logger.warning(f"Failed to load model with {device}, falling back to CPU: {e}")
                try:
                    self.model = WhisperModel(
                        model_size,
                        device="cpu",
                        compute_type="int8"
                    )
                    logger.info("Whisper model loaded successfully (CPU mode)")
                except Exception as cpu_error:
                    logger.error(f"Failed to load Whisper model even with CPU: {cpu_error}")
                    raise
            else:
                logger.error(f"Failed to load Whisper model: {e}")
                raise

        self.language = config["whisper"]["language"]
        self.beam_size = config["whisper"]["beam_size"]
        self.vad_filter = config["whisper"]["vad_filter"]

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> Optional[str]:
        """Transcribe audio to text"""
        try:
            # Ensure audio is float32 and normalized
            if audio.dtype != np.float32:
                audio = audio.astype(np.float32)

            # Normalize audio to [-1, 1]
            max_val = np.max(np.abs(audio))
            if max_val > 0:
                audio = audio / max_val

            # Transcribe
            segments, info = self.model.transcribe(
                audio,
                language=self.language,
                beam_size=self.beam_size,
                vad_filter=self.vad_filter,
                without_timestamps=True
            )

            # Collect all segments
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text.strip())

            result = " ".join(text_parts).strip()

            if result:
                logger.info(f"Transcribed ({info.language}): {result}")
                return result

            return None

        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return None


class WebSocketServer:
    """WebSocket server to send transcriptions to browser"""

    def __init__(self, config: Config):
        self.config = config
        self.host = config["websocket"]["host"]
        self.port = config["websocket"]["port"]
        self.clients = set()
        self.server = None
        self.on_config_update = None  # Callback for config updates

    async def register(self, websocket):
        """Register new client"""
        self.clients.add(websocket)
        logger.info(f"Client connected. Total clients: {len(self.clients)}")

    async def unregister(self, websocket):
        """Unregister client"""
        self.clients.discard(websocket)
        logger.info(f"Client disconnected. Total clients: {len(self.clients)}")

    async def handler(self, websocket):
        """Handle WebSocket connection"""
        await self.register(websocket)
        try:
            # Keep connection alive and handle messages from browser
            async for message in websocket:
                try:
                    data = json.loads(message)
                    logger.info(f"Received from browser: {data}")

                    # Handle config updates from browser
                    if data.get('type') == 'config':
                        if self.on_config_update:
                            self.on_config_update(data)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from client: {message}")
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.unregister(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast message to all connected clients"""
        if not self.clients:
            return

        message_json = json.dumps(message, ensure_ascii=False)

        # Send to all clients
        disconnected = set()
        for client in self.clients:
            try:
                await client.send(message_json)
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(client)

        # Remove disconnected clients
        for client in disconnected:
            await self.unregister(client)

    async def start(self):
        """Start WebSocket server"""
        self.server = await websockets.serve(
            self.handler,
            self.host,
            self.port
        )
        logger.info(f"WebSocket server started on ws://{self.host}:{self.port}")

        # Keep server running
        await asyncio.Future()  # Run forever


class SpeechCaptureApp:
    """Main application coordinating all components"""

    def __init__(self):
        self.config = Config()
        self.audio_capture = AudioCapture(self.config)
        self.recognizer = SpeechRecognizer(self.config)
        self.ws_server = WebSocketServer(self.config)
        self.is_running = False

        # Set up config update callback
        self.ws_server.on_config_update = self.handle_config_update

    def handle_config_update(self, config_data: Dict[str, Any]):
        """Handle configuration updates from browser"""
        if 'language' in config_data:
            new_lang = config_data['language']
            logger.info(f"Browser requested language change: {new_lang}")

            # Normalize language code (e.g., 'en-US' -> 'en', 'ja-JP' -> 'ja')
            if new_lang and '-' in new_lang:
                new_lang = new_lang.split('-')[0]
                logger.info(f"Normalized language code to: {new_lang}")

            # Update recognizer language
            self.recognizer.language = new_lang
            logger.info(f"Speech recognition language updated to: {new_lang}")

    async def process_audio_loop(self):
        """Main loop for processing audio"""
        logger.info("Audio processing loop started")

        while self.is_running:
            # Get audio chunk
            audio = self.audio_capture.get_audio_chunk()

            if audio is not None:
                # Transcribe
                text = self.recognizer.transcribe(
                    audio,
                    self.config["audio"]["sample_rate"]
                )

                if text:
                    # Send to browser
                    message = {
                        "type": "transcription",
                        "text": text,
                        "timestamp": time.time(),
                        "language": self.config["whisper"]["language"]
                    }
                    await self.ws_server.broadcast(message)

            # Small delay to prevent CPU spinning
            await asyncio.sleep(0.1)

    async def run(self):
        """Run the application"""
        try:
            logger.info("Starting VanillaChanny Hardware Speech Capture...")

            # Start audio capture
            self.audio_capture.start()

            # Set running flag
            self.is_running = True

            # Start both WebSocket server and audio processing
            await asyncio.gather(
                self.ws_server.start(),
                self.process_audio_loop()
            )

        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        except Exception as e:
            logger.error(f"Application error: {e}", exc_info=True)
        finally:
            self.shutdown()

    def shutdown(self):
        """Shutdown application"""
        logger.info("Shutting down...")
        self.is_running = False
        self.audio_capture.stop()
        logger.info("Shutdown complete")


def main():
    """Main entry point"""
    print("=" * 60)
    print("VanillaChanny Hardware Speech Capture")
    print("Desktop application for high-quality speech recognition")
    print("=" * 60)
    print()

    # Show available audio devices
    print("Available audio devices:")
    print(sd.query_devices())
    print()

    # Create and run application
    app = SpeechCaptureApp()

    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
