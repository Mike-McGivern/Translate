# jimakuChan GUI Desktop Application

Modern desktop application for real-time speech recognition and subtitles with OBS integration.

## 🎯 Phase 1 - COMPLETE!

✅ GUI with settings panel
✅ Setup wizard (OBS-style)
✅ Live audio level meter
✅ Noise gate with dB visualization
✅ Whisper speech recognition
✅ Text file output for OBS

## 🚀 Quick Start

### Installation

**1. Install GUI dependencies:**
```bash
cd HardwareTools
pip install -r requirements_gui.txt
```

**2. Launch the app:**
```bash
# Windows
start_gui.bat

# Or directly
python gui_app.py
```

### First-Time Setup

**1. Click "🧙 Setup Wizard"**

The wizard will guide you through:
- **Step 1:** Microphone selection and testing
- **Step 2:** Noise gate calibration (speak test sentence)
- **Step 3:** Whisper model selection
- **Step 4:** Review and save

**2. Start Recognition**

Click "▶️ Start Recognition" to begin!

## 📊 Features

### Audio Level Meter
- Real-time dB display
- Visual gate open/closed indicator
- Color-coded levels (green = good, red = too loud)

### Noise Gate
- **Threshold slider:** -60dB to -20dB
- **Release time:** 0.2s to 2.0s
- **Auto-calibrate:** Analyzes your voice and sets optimal threshold

### Whisper Models
- **Tiny:** Fastest, lowest accuracy (~1GB RAM)
- **Base:** Fast, good for real-time (~1GB RAM)
- **Small:** Balanced, recommended (~2GB RAM) ⭐
- **Medium:** High accuracy (~5GB RAM)
- **Large:** Best accuracy (~10GB RAM)

### OBS Integration

**Text File Output:**
```
HardwareTools/subtitles.txt
```

**How to add to OBS:**
1. Add Source → Text (GDI+)
2. Check "Read from file"
3. Browse to `HardwareTools/subtitles.txt`
4. Customize font, color, size
5. Done! Text updates automatically

## 🎛️ Main Window

### Settings Panel (Left)
- **Audio Device:** Select microphone
- **Noise Gate:**
  - Threshold slider (when gate opens)
  - Release time (how long after silence)
- **Whisper Model:** Choose accuracy vs speed
- **Language:** Speech recognition language

### Monitor Panel (Right)
- **Audio Level Meter:** Real-time visualization
- **Latest Transcription:** See recognized text
- **Output Status:** File path and status

### Control Panel (Bottom)
- **▶️ Start Recognition:** Begin speech-to-text
- **🧙 Setup Wizard:** Re-run configuration

## 💡 Tips

### Getting Best Accuracy

1. **Use Setup Wizard** - Auto-calibrates for your voice
2. **Speak clearly** - Enunciate, moderate pace
3. **Good mic position** - 6-12 inches from mouth
4. **Quiet environment** - Minimize background noise
5. **Adjust gate** - Set just below your speaking level

### Troubleshooting

**Gate not opening?**
- Threshold too high → lower the slider
- Mic too quiet → speak louder or boost mic gain

**Gate stays open?**
- Threshold too low → raise the slider
- Background noise → find quieter location

**Cutting off sentences?**
- Release time too short → increase release time

**Poor accuracy?**
- Try larger model (base → small → medium)
- Check language setting matches what you speak
- Run setup wizard again

## 🔮 Coming Next: Phase 2

- [ ] Translation integration (Google Translate)
- [ ] Styled subtitle preview window
- [ ] Font and color customization
- [ ] Multiple output languages
- [ ] Browser source server
- [ ] Custom styling templates

## 📁 Files

```
HardwareTools/
├── gui_app.py              # Main GUI application
├── setup_wizard.py         # Setup wizard
├── speech_capture.py       # Audio & recognition (from CLI)
├── requirements_gui.txt    # GUI dependencies
├── start_gui.bat          # Windows launcher
├── config.json            # Settings (auto-saved)
└── subtitles.txt          # Output (OBS reads this)
```

## ⌨️ Keyboard Shortcuts

- **Escape:** Stop recognition
- **F1:** Open setup wizard
- **Ctrl+Q:** Quit application

## 🎨 Customization

Settings are saved to `config.json` automatically. You can also edit manually:

```json
{
  "audio": {
    "device": 1,
    "gate_threshold_db": -35,
    "gate_release_time": 0.8
  },
  "whisper": {
    "model_size": "small",
    "language": "en"
  }
}
```

## 🆘 Support

- Check console for detailed logs
- Report issues with log output
- Include your config.json
- Describe what you were doing when error occurred

---

**Enjoy high-quality speech recognition!** 🎤✨
