from typing import Dict, Any

class VoiceService:
    @staticmethod
    def get_voice_config(language: str = "en") -> Dict[str, Any]:
        voice_map = {
            "en": {"lang_tag": "en-IN", "voice_name": "Google English (India)", "pitch": 1.0, "rate": 1.0},
            "hi": {"lang_tag": "hi-IN", "voice_name": "Google हिन्दी", "pitch": 1.0, "rate": 0.95},
            "te": {"lang_tag": "te-IN", "voice_name": "Google తెలుగు", "pitch": 1.0, "rate": 0.95},
            "ta": {"lang_tag": "ta-IN", "voice_name": "Google தமிழ்", "pitch": 1.0, "rate": 0.95},
            "ml": {"lang_tag": "ml-IN", "voice_name": "Google മലയാളം", "pitch": 1.0, "rate": 0.95}
        }
        return voice_map.get(language, voice_map["en"])

voice_service = VoiceService()
