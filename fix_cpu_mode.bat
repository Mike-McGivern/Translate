@echo off
echo ================================================
echo Fixing CUDA/CPU Mode Issues
echo Reinstalling faster-whisper for CPU-only mode
echo ================================================
echo.

cd /d "%~dp0"

echo Uninstalling current packages...
pip uninstall -y faster-whisper ctranslate2

echo.
echo Installing CPU-only versions with all dependencies...
pip install requests huggingface-hub tokenizers onnxruntime
pip install ctranslate2==4.0.0
pip install faster-whisper==1.0.3

echo.
echo Done! Now try running start_speech_capture.bat again.
echo.
pause
