"""
Simple translation client using Google Translate
"""

import logging
import urllib.parse
import urllib.request
import json

logger = logging.getLogger(__name__)


class Translator:
    """Simple Google Translate client"""

    def __init__(self):
        # Using free Google Translate endpoint
        self.base_url = "https://translate.googleapis.com/translate_a/single"

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """Translate text from source to target language

        Args:
            text: Text to translate
            source_lang: Source language code (e.g., 'en', 'ja', 'es')
            target_lang: Target language code

        Returns:
            Translated text, or original text if translation fails
        """
        if not text or not target_lang:
            return text

        # If source and target are the same, no translation needed
        if source_lang == target_lang:
            return text

        try:
            # Prepare request parameters
            params = {
                'client': 'gtx',
                'sl': source_lang or 'auto',
                'tl': target_lang,
                'dt': 't',
                'q': text
            }

            # Build URL
            url = f"{self.base_url}?{urllib.parse.urlencode(params)}"

            # Make request
            headers = {'User-Agent': 'Mozilla/5.0'}
            req = urllib.request.Request(url, headers=headers)

            with urllib.request.urlopen(req, timeout=5) as response:
                result = json.loads(response.read().decode('utf-8'))

                # Extract translated text
                if result and len(result) > 0 and result[0]:
                    translated_parts = [part[0] for part in result[0] if part[0]]
                    translated = ''.join(translated_parts)
                    logger.info(f"Translated ({source_lang}→{target_lang}): {text[:50]}... → {translated[:50]}...")
                    return translated

        except Exception as e:
            logger.error(f"Translation failed ({source_lang}→{target_lang}): {e}")

        # Return original text if translation fails
        return text

    def translate_batch(self, text: str, source_lang: str, target_langs: list) -> dict:
        """Translate text to multiple target languages

        Args:
            text: Text to translate
            source_lang: Source language code
            target_langs: List of target language codes

        Returns:
            Dict mapping language codes to translated text
        """
        results = {}
        for target_lang in target_langs:
            if target_lang and target_lang != 'none':
                results[target_lang] = self.translate(text, source_lang, target_lang)
        return results
