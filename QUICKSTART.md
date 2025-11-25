# Quick Start Guide

Get started with jimakuChan Hardware Tools in 3 easy steps!

## Prerequisites

- **Python 3.8+** - [Download here](https://www.python.org/downloads/)
- **FFmpeg** - Required for audio processing

### Installing FFmpeg on Windows

**Option 1: Using Chocolatey (Recommended)**
```bash
choco install ffmpeg
```

**Option 2: Manual Installation**
1. Download from [ffmpeg.org](https://ffmpeg.org/download.html)
2. Extract to `C:\ffmpeg`
3. Add `C:\ffmpeg\bin` to your system PATH

### Installing FFmpeg on macOS
```bash
brew install ffmpeg
```

### Installing FFmpeg on Linux
```bash
sudo apt install ffmpeg  # Debian/Ubuntu
sudo yum install ffmpeg  # CentOS/RHEL
```

## Step 1: Install Dependencies

Double-click `start_speech_capture.bat` - it will automatically install dependencies on first run.

Or manually install:
```bash
cd HardwareTools
pip install -r requirements.txt
```

## Step 2: Configure Settings (Optional)

Edit `config.json` to customize:

### Common Configurations

**English speech recognition:**
```json
{
  "whisper": {
    "model_size": "base",
    "language": "en"
  }
}
```

**Higher accuracy (requires more RAM):**
```json
{
  "whisper": {
    "model_size": "small",
    "language": "ja"
  }
}
```

**GPU acceleration (NVIDIA only):**
```json
{
  "whisper": {
    "model_size": "medium",
    "device": "cuda",
    "compute_type": "float16"
  }
}
```

## Step 3: Start the Application

### On Windows
Double-click `start_speech_capture.bat`

### On macOS/Linux
```bash
python speech_capture.py
```

You should see:
```
jimakuChan Hardware Speech Capture
Desktop application for high-quality speech recognition
============================================================

Available audio devices:
  0 Microsoft Sound Mapper - Input
  1 Microphone (Realtek High Definition Audio)
  ...

INFO - WebSocket server started on ws://localhost:8765
INFO - Audio capture started
INFO - Audio processing loop started
```

## Step 4: Connect Browser

1. Open `index.html` in your browser
2. Scroll to **音声認識エンジン** (Speech Recognition Engine)
3. Select **デスクトップアプリ (高品質)** / **Desktop App (High Quality)**
4. Click **字幕を表示** (Show Subtitles)

The browser will connect to the desktop app and start showing subtitles!

## Troubleshooting

### "Failed to connect to desktop app"
- Make sure `speech_capture.py` is running
- Check Windows Firewall isn't blocking port 8765
- Try running: `netstat -an | find "8765"` to verify the server is listening

### "No module named 'faster_whisper'"
```bash
pip install faster-whisper
```

### "Could not find FFmpeg"
- Install FFmpeg (see Prerequisites above)
- Verify with: `ffmpeg -version`

### Poor Recognition Accuracy
1. Try a larger model size in `config.json`:
   - `tiny` → `base` → `small` → `medium`
2. Ensure correct language is set
3. Check microphone input levels

### GPU Not Detected
1. Install CUDA Toolkit: https://developer.nvidia.com/cuda-downloads
2. Reinstall faster-whisper with CUDA support:
   ```bash
   pip uninstall faster-whisper
   pip install faster-whisper[cuda]
   ```

### High CPU/Memory Usage
Use a smaller model:
```json
{
  "whisper": {
    "model_size": "tiny"
  }
}
```

## Model Size Comparison

| Model  | Parameters | RAM Usage | Speed    | Accuracy |
|--------|-----------|-----------|----------|----------|
| tiny   | 39M       | ~1 GB     | Fastest  | Low      |
| base   | 74M       | ~1 GB     | Fast     | Good     |
| small  | 244M      | ~2 GB     | Medium   | Better   |
| medium | 769M      | ~5 GB     | Slow     | Great    |
| large  | 1550M     | ~10 GB    | Slowest  | Best     |

**Recommendation:** Start with `base` for real-time streaming, use `small` or higher for better accuracy.

## Advanced Configuration

### Custom Audio Device

List available devices:
```python
python -c "import sounddevice as sd; print(sd.query_devices())"
```

Set device in `config.json`:
```json
{
  "audio": {
    "device": 1
  }
}
```

### Custom WebSocket Port

If port 8765 is already in use:

`config.json`:
```json
{
  "websocket": {
    "port": 9999
  }
}
```

Then add to browser URL:
```
index.html?desktopPort=9999
```

### Multi-language Auto-detection

Set language to `null` for automatic detection:
```json
{
  "whisper": {
    "language": null
  }
}
```

## Support

For issues or questions:
- Check the main [README.md](README.md)
- Report bugs: Create an issue on GitHub
- Documentation: See main project README

## Next Steps

- Fine-tune `config.json` for your use case
- Try different model sizes
- Experiment with GPU acceleration
- Customize subtitle styling in `index.html`

Enjoy high-quality speech recognition! 🎤✨
