"""
Language Manager for GUI Internationalization
Supports English, Spanish, and Japanese
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional


class LanguageManager:
    """Manages GUI language translations"""

    SUPPORTED_LANGUAGES = {
        "en": "English",
        "es": "Español",
        "ja": "日本語"
    }

    def __init__(self, language_code: str = "en"):
        self.languages_dir = Path(__file__).parent / "languages"
        self.current_language = language_code
        self.translations: Dict[str, Any] = {}
        self.load_language(language_code)

    def load_language(self, language_code: str) -> bool:
        """Load language file"""
        if language_code not in self.SUPPORTED_LANGUAGES:
            print(f"Warning: Language '{language_code}' not supported, falling back to English")
            language_code = "en"

        language_file = self.languages_dir / f"{language_code}.json"

        if not language_file.exists():
            print(f"Error: Language file not found: {language_file}")
            return False

        try:
            with open(language_file, 'r', encoding='utf-8') as f:
                self.translations = json.load(f)
            self.current_language = language_code
            print(f"Loaded language: {self.SUPPORTED_LANGUAGES[language_code]}")
            return True
        except Exception as e:
            print(f"Error loading language file: {e}")
            return False

    def get(self, key: str, **kwargs) -> str:
        """Get translated string by key

        Supports nested keys with dot notation: 'wizard.title'
        Supports string formatting: get('threshold_value', value=-40)
        """
        # Handle nested keys
        keys = key.split('.')
        value = self.translations

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return f"[Missing: {key}]"

        # Format string if kwargs provided
        if kwargs and isinstance(value, str):
            try:
                return value.format(**kwargs)
            except KeyError as e:
                print(f"Warning: Missing format key {e} for '{key}'")
                return value

        return value if isinstance(value, str) else f"[Invalid: {key}]"

    def switch_language(self, language_code: str) -> bool:
        """Switch to a different language"""
        return self.load_language(language_code)

    def get_current_language(self) -> str:
        """Get current language code"""
        return self.current_language

    def get_language_name(self, code: Optional[str] = None) -> str:
        """Get language name for a code (or current language if None)"""
        code = code or self.current_language
        return self.SUPPORTED_LANGUAGES.get(code, "Unknown")

    def get_available_languages(self) -> Dict[str, str]:
        """Get dict of available languages {code: name}"""
        return self.SUPPORTED_LANGUAGES.copy()
