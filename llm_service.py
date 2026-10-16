import re
import logging
from typing import Dict, Any, Tuple, Optional, List
from datetime import datetime, timezone
from app.core.config import settings
from app.services.weather_service import weather_service
from app.core.constants import KNOWN_CITY_COORDINATES, DEFAULT_CITIES

logger = logging.getLogger("weathergpt")

class LLMService:
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.model_name = settings.GEMINI_MODEL
        self._gemini_client = None
        if self.api_key:
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Could not initialize Gemini Client: {e}")
                self._gemini_client = None

        # Short-term in-memory conversation memory keyed by session_id
        self.sessions: Dict[str, Dict[str, Any]] = {}

    def detect_language(self, message: str, fallback_lang: str = "en") -> str:
        """Detect language from query script or explicit language request keywords"""
        m = message.lower()
        if any(w in m for w in ["in telugu", "telugu lo", "తెలుగులో", "తెలుగు"]):
            return "te"
        if any(w in m for w in ["in hindi", "hindi me", "हिन्दी में", "हिंदी में", "हिन्दी", "हिंदी"]):
            return "hi"
        if any(w in m for w in ["in tamil", "tamilil", "தமிழில்", "தமிழ்"]):
            return "ta"
        if any(w in m for w in ["in malayalam", "malayalathil", "മലയാളത്തിൽ", "മലയാളം"]):
            return "ml"
        if any(w in m for w in ["in english", "english lo"]):
            return "en"

        # Check Unicode script ranges
        if re.search(r'[\u0c00-\u0c7f]', message):
            return "te"
        if re.search(r'[\u0900-\u097f]', message):
            return "hi"
        if re.search(r'[\u0b80-\u0bff]', message):
            return "ta"
        if re.search(r'[\u0d00-\u0d7f]', message):
            return "ml"

        return fallback_lang or "en"

    def extract_location(self, message: str, default_city: Optional[str] = None) -> Optional[str]:
        """Extract city name from query text across English, Telugu, Hindi, Tamil, Malayalam scripts"""
        msg_lower = message.lower()

        # 1. Match against KNOWN_CITY_COORDINATES keys (handles Telugu, Hindi, Tamil, Malayalam, and aliases)
        # Sort by length descending to match multi-word names first (e.g. "new delhi" before "delhi")
        sorted_known = sorted(KNOWN_CITY_COORDINATES.keys(), key=lambda k: len(k), reverse=True)
        for k in sorted_known:
            if k in msg_lower or k in message:
                return KNOWN_CITY_COORDINATES[k]["name"]

        # 2. Check Indian language suffixes / postpositions
        # Telugu: "... లో" (విశాఖపట్నంలో, హైదరాబాదులో, కర్నూలులో)
        te_match = re.search(r'([A-Za-z\u0c00-\u0c7f]+)\s*లొ|([A-Za-z\u0c00-\u0c7f]+)లో', message)
        if te_match:
            c = (te_match.group(1) or te_match.group(2) or "").strip()
            if len(c) > 2 and c.lower() not in {"ఈరోజు", "వాతావరణం", "రేపు", "వారం"}:
                c_lower = c.lower()
                if c_lower in KNOWN_CITY_COORDINATES:
                    return KNOWN_CITY_COORDINATES[c_lower]["name"]
                return c.title()

        # Hindi: "... में" (दिल्ली में, जयपुर में, लखनऊ में)
        hi_match = re.search(r'([A-Za-z\u0900-\u097f]+)\s+में', message)
        if hi_match:
            c = hi_match.group(1).strip()
            if len(c) > 2 and c not in {"आज", "कल", "मौसम", "तापमान", "बारिश"}:
                c_lower = c.lower()
                if c_lower in KNOWN_CITY_COORDINATES:
                    return KNOWN_CITY_COORDINATES[c_lower]["name"]
                return c.title()

        # Tamil: "... ல் / இல்"
        ta_match = re.search(r'([A-Za-z\u0b80-\u0bff]+)(?:ல்|இல்)\b', message)
        if ta_match:
            c = ta_match.group(1).strip()
            if len(c) > 2:
                c_lower = c.lower()
                if c_lower in KNOWN_CITY_COORDINATES:
                    return KNOWN_CITY_COORDINATES[c_lower]["name"]
                return c.title()

        # Malayalam: "... ൽ / യിൽ"
        ml_match = re.search(r'([A-Za-z\u0d00-\u0d7f]+)(?:ൽ|യിൽ)\b', message)
        if ml_match:
            c = ml_match.group(1).strip()
            if len(c) > 2:
                c_lower = c.lower()
                if c_lower in KNOWN_CITY_COORDINATES:
                    return KNOWN_CITY_COORDINATES[c_lower]["name"]
                return c.title()

        # 3. Check English prepositions "in City", "at City", "for City", "near City"
        match = re.search(r'\b(?:in|at|for|near|of|to)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)', message, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            stop_words = {
                "today", "tomorrow", "this", "next", "the", "my", "our", "india",
                "week", "month", "morning", "afternoon", "evening", "night", "now",
                "here", "there", "weather", "forecast", "climate", "temperature", "rain"
            }
            if candidate.lower() not in stop_words and len(candidate) > 2:
                return candidate.title()

        return default_city or "Visakhapatnam"

    def detect_timeframe(self, message: str, previous_timeframe: Optional[str] = None) -> str:
        """Detect timeframe: current, tomorrow, hourly, 7day, weekend"""
        m = message.lower()
        if any(w in m for w in ["tomorrow", "\u0c30\u0c47\u0c2a\u0c41", "\u0915\u0932", "\u0ba8\u0bbe\u0bb3\u0bc8", "\u0ba8\u0bbe\u0bb3\u0bc8\u0b95\u0bcd\u0b95\u0bc1", "\u0d28\u0d3e\u0d33\u0d46"]):
            return "tomorrow"
        elif any(w in m for w in ["hourly", "hour by hour", "next few hours", "\u0c17\u0c02\u0c1f\u0c32\u0c35\u0c3e\u0c30\u0c40", "\u0918\u0902\u091f\u0947 \u0926\u0930 \u0918\u0902\u091f\u0947", "\u0bae\u0ba3\u0bbf\u0ba8\u0bc7\u0bb0", "\u0d2e\u0d23\u0d3f\u0d15\u0d4d\u0d15\u0d42\u0d7c"]):
            return "hourly"
        elif any(w in m for w in ["7 day", "7-day", "7 days", "week", "weekly", "\u0c35\u0c3e\u0c30\u0c02", "\u0939\u092b\u094d\u0924\u093e", "\u0bb5\u0bbe\u0bb0\u0bae\u0bcd", "\u0d06\u0d34\u0d4d\u0d1a"]):
            return "7day"
        elif any(w in m for w in ["weekend", "saturday", "sunday", "\u0c35\u0c40\u0c15\u0c46\u0c02\u0c21\u0c4d", "\u0938\u092a\u094d\u0924\u093e\u0939\u093e\u0902\u0924", "\u0bb5\u0bbe\u0bb0 \u0b87\u0bb1\u0bc1\u0ba4\u0bbf"]):
            return "weekend"
        elif previous_timeframe and any(w in m for w in ["what about", "and", "how about", "tell me about", "\u0c2e\u0c30\u0c3f", "\u0914\u0930", "\u0bae\u0bb1\u0bcd\u0bb1\u0bc1\u0bae\u0bcd"]):
            return previous_timeframe
        return "current"

    def detect_intent(
        self,
        message: str,
        previous_intent: Optional[str] = None,
        previous_timeframe: Optional[str] = None
    ) -> str:
        """
        Categorize intent:
        temperature, rain_check, rain_probability, tomorrow_forecast, hourly,
        forecast_7d, umbrella, wind, humidity, sunrise_sunset, alerts, travel_safety, agriculture, current
        """
        m = message.lower()

        if any(w in m for w in ["sunrise", "sunset", "dawn", "dusk", "\u0c38\u0c42\u0c30\u0c4d\u0c2f\u0c4b\u0c26\u0c2f\u0c02", "\u0c38\u0c42\u0c30\u0c4d\u0c2f\u0c3e\u0c38\u0c4d\u0c24\u0c2e\u0c2f\u0c02", "\u0938\u0942\u0930\u094d\u092f\u094b\u0926\u092f", "\u0938\u0942\u0930\u094d\u092f\u093e\u0938\u094d\u0924", "\u0b9a\u0bc2\u0bb0\u0bbf\u0b8f \u0b89\u0ba4\u0baf\u0bae\u0bcd", "\u0b9a\u0bc2\u0bb0\u0bbf\u0b8f \u0b85\u0bb8\u0bcd\u0ba4\u0bae\u0ba9\u0bae\u0bcd", "\u0d38\u0d42\u0d30\u0d4d\u0d2f\u0d4b\u0d26\u0d2f\u0d02", "\u0d38\u0d42\u0d30\u0d4d\u0d2f\u0d3e\u0d38\u0d4d\u0d24\u0d2e\u0d2f\u0d02"]):
            return "sunrise_sunset"

        if any(w in m for w in ["probability", "chance of rain", "rain chance", "percentage", "\u0c0e\u0c02\u0c24 \u0c36\u0c3e\u0c24\u0c02", "\u0c05\u0c35\u0c15\u0c3e\u0c36\u0c02", "\u0938\u0902\u092d\u093e\u0935\u0928\u093e", "\u0bb5\u0bbe\u0baf\u0bcd\u0baa\u0bcd\u0baa\u0bc1", "\u0d38\u0d3e\u0d27\u0d4d\u0d2f\u0d24"]):
            return "rain_probability"

        if any(w in m for w in ["travel", "trip", "drive", "outdoor", "safe to travel", "road", "journey", "highway", "\u0c2a\u0c4d\u0c30\u0c2f\u0c3e\u0c23\u0c02", "\u0c30\u0c4b\u0c21\u0c4d\u0c21\u0c41", "\u092f\u093e\u0924\u094d\u0930\u093e", "\u0938\u092b\u093c\u0930", "\u0baa\u0baf\u0ba3\u0bae\u0bcd", "\u0d2f\u0d3e\u0d24\u0d4d\u0d30"]):
            return "travel_safety"

        if any(w in m for w in ["alert", "warning", "cyclone", "flood", "danger", "storm", "thunderstorm", "\u0c39\u0c46\u0c1a\u0c4d\u0c1a\u0c30\u0c3f\u0c15", "\u0c24\u0c41\u0c2b\u0c3e\u0c28\u0c41", "\u0c35\u0c30\u0c26", "\u091a\u0947\u0924\u093e\u0935\u0928\u0940", "\u0924\u0942\u092b\u093e\u0928", "\u092c\u093e\u0922\u093c", "\u0b8e\u0b9a\u0bcd\u0b8a\u0bb0\u0bbf\u0b95\u0bcd\u0b95\u0bc8", "\u0baa\u0bc1\u0baf\u0bb2\u0bcd", "\u0d2e\u0d41\u0d28\u0d4d\u0ba8\u0bb1\u0bbf\u0baf\u0bbf\u0baa\u0bcd\u0baa\u0bcd"]):
            return "alerts"

        if any(w in m for w in ["umbrella", "raincoat", "\u091b\u0924\u0930\u0940", "\u091b\u093e\u0924\u093e", "\u0c17\u0c4a\u0c21\u0c41\u0c17\u0c41", "\u0c30\u0c46\u0c2f\u0c3f\u0c28\u0c4d\u200c\u0c15\u0c4b\u0c1f\u0c4d", "\u0b95\u0bc1\u0b9f\u0bc8", "\u0d15\u0d41\u0d1f", "carry"]):
            return "umbrella"

        if any(w in m for w in ["farm", "farming", "crop", "agriculture", "farmer", "irrigation", "pesticide", "sow", "\u0c30\u0c48\u0c24\u0c41", "\u0c35\u0c4d\u0c2f\u0c35\u0c38\u0c3e\u0c2f\u0c02", "\u0c2a\u0c02\u0c1f", "\u0c38\u0c3e\u0c17\u0c41", "\u0916\u0947\u0924\u0940", "\u0915\u093f\u0938\u093e\u0928", "\u092b\u0938\u0932", "\u0bb5\u0bbf\u0bb5\u0b8a\u0baf\u0bae\u0bcd", "\u0d15\u0d43\u0d37\u0d3f"]):
            return "agriculture"

        if any(w in m for w in ["wind", "gust", "breeze", "stormy", "\u0c17\u0c3e\u0c32\u0c3f", "\u0c17\u0c3e\u0c32\u0c41\u0c32\u0c41", "\u0939\u0935\u093e", "\u0906\u0902\u0927\u0940", "\u0b95\u0bbe\u0bb1\u0bcd\u0bb1\u0bc1", "\u0d15\u0d3e\u0d1f\u0d4d\u0d31\u0d4d"]):
            return "wind"

        if any(w in m for w in ["humidity", "moisture", "dew", "\u0928\u092e\u0940", "\u0909\u092e\u0938", "\u0c24\u0c47\u0c2e", "\u0c09\u0c15\u0c4d\u0c15\u0c2a\u0c4b\u0c24", "\u0b88\u0bb0\u0baa\u0bcd\u0baa\u0ba4\u0bae\u0bcd", "\u0d08\u0d7c\u0baa\u0bcd\u0baa\u0d02"]):
            return "humidity"

        if any(w in m for w in ["7 day", "7-day", "7 days", "week", "weekly", "\u0c35\u0c3e\u0c30\u0c02", "\u0939\u092b\u094d\u0924\u093e", "\u0bb5\u0bbe\u0bb0", "\u0d06\u0d34\u0d4d\u0d1a", "forecast"]):
            return "forecast_7d"

        if any(w in m for w in ["hourly", "hour by hour", "\u0c17\u0c02\u0c1f\u0c32\u0c35\u0c3e\u0c30\u0c40", "\u0918\u0902\u091f\u0947 \u0926\u0930 \u0918\u0902\u091f\u0947"]):
            return "hourly"

        if any(w in m for w in ["rain", "raining", "rainy", "shower", "drizzle", "\u0c35\u0c30\u0c4d\u0c37\u0c02", "\u0c35\u0c3e\u0c28", "\u0c1c\u0c32\u0c4d\u0c32\u0c41", "\u092c\u093e\u0930\u093f\u0936", "\u092c\u0930\u0938\u093e\u0924", "\u0bae\u0bb4\u0bc8", "\u0d2e\u0d34"]):
            return "rain_check"

        if any(w in m for w in ["tomorrow", "\u0c30\u0c47\u0c2a\u0c41", "\u0915\u0932", "\u0ba8\u0bbe\u0bb3\u0bc8", "\u0d28\u0d3e\u0d33\u0d46"]):
            return "tomorrow_forecast"

        if any(w in m for w in ["temp", "temperature", "hot", "cold", "celsius", "\u0924\u093e\u092a\u092e\u093e\u0928", "\u0917\u0930\u094d\u092e", "\u0920\u0902\u0921", "\u0c09\u0c37\u0c4d\u0c23\u0c4b\u0c17\u0c4d\u0c30\u0c24", "\u0c21\u0c3f\u0c17\u0c4d\u0c30\u0c40\u0c32\u0c41", "\u0c1a\u0c32\u0c3f", "\u0c0e\u0c02\u0c21", "\u0bb5\u0bc6\u0baa\u0bcd\u0baa\u0ba8\u0bbf\u0bb2\u0bc8", "\u0d24\u0d3e\u0d2a\u0d28\u0d3f\u0d32"]):
            return "temperature"

        if previous_intent and any(w in m for w in ["what about", "how about", "and", "\u0c2e\u0c30\u0c3f", "\u0c07\u0c02\u0c15\u0c3e", "\u0914\u0930"]):
            return previous_intent

        return "current"

    def _get_missing_location_response(self, lang: str) -> str:
        """Polite prompt asking which city or location the user wants weather for"""
        if lang == "te":
            return "దయచేసి మీరు ఏ నగరం లేదా ప్రాంతం కోసం వాతావరణ సమాచారాన్ని తెలుసుకోవాలనుకుంటున్నారో తెలియజేయండి (ఉదాహరణకు: 'విశాఖపట్నంలో వాతావరణం', 'హైదరాబాద్‌లో ఉష్ణోగ్రత')."
        elif lang == "hi":
            return "कृपया बताएं कि आप किस शहर या स्थान का मौसम जानना चाहते हैं? (उदाहरण: 'दिल्ली में मौसम', 'मुंबई का तापमान')."
        elif lang == "ta":
            return "எந்த நகரம் அல்லது இடத்திற்கான வானிலை விவரங்களை அறிய விரும்புகிறீர்கள்? (எ.கா: 'சென்னை வானிலை', 'மதுரை வெப்பநிலை')."
        elif lang == "ml":
            return "ഏത് നഗരത്തിലെ കാലാവസ്ഥ വിവരമാണ് അറിയാൻ ആഗ്രഹിക്കുന്നത് എന്ന് ദയവായി വ്യക്തമാക്കുക (ഉദാ: 'കൊച്ചി കാലാവസ്ഥ', 'തിരുവനന്തപുരം താപനില')."
        return "Which city or location would you like the weather for? (e.g., 'weather in Vizag', 'Delhi temperature', 'rain in Mumbai')."

    def _generate_grounded_fallback(
        self,
        intent: str,
        timeframe: str,
        city: str,
        context: Dict[str, Any],
        lang: str
    ) -> Tuple[str, List[str]]:
        """
        High-quality grounded natural-language responses in 5 Indian languages
        derived strictly from real-time meteorological feed.
        """
        cur = context.get("current", {})
        daily = context.get("daily", [])
        hourly = context.get("hourly", [])
        alerts = context.get("alerts", {})
        advisories = context.get("advisories", {})

        temp = cur.get("temperature", 0.0)
        feels_like = cur.get("feels_like", temp)
        cond = cur.get("condition", "Clear Sky")
        humidity = cur.get("humidity", 60)
        wind = cur.get("wind_speed", 10.0)
        wind_compass = cur.get("wind_compass", "NE")
        pressure = cur.get("pressure", 1013.0)
        rain_prob = cur.get("rain_probability", 0)
        uv = cur.get("uv_index", 5.0)
        precip = float(cur.get("precipitation", 0.0) or 0.0)
        cape = float(cur.get("cape", 0.0) or 0.0)
        code = int(cur.get("weather_code", 0))
        sunrise = cur.get("sunrise", "06:00")
        sunset = cur.get("sunset", "18:30")
        has_alerts = alerts.get("has_alerts", False)
        is_active_rain_or_storm = (precip > 1.0) or (80 <= code <= 99)

        # Tomorrow's metrics from daily[1]
        t_day = daily[1] if len(daily) > 1 else (daily[0] if daily else {})
        t_temp_max = t_day.get("temp_max", temp + 1.0)
        t_temp_min = t_day.get("temp_min", temp - 4.0)
        t_cond = t_day.get("condition", cond)
        t_rain_prob = t_day.get("rain_probability", rain_prob)
        t_code = t_day.get("weather_code", code)
        t_sunrise = t_day.get("sunrise", sunrise)
        t_sunset = t_day.get("sunset", sunset)

        # ----------------------------------------------------------------------
        # TELUGU (te) Grounded Responses
        # ----------------------------------------------------------------------
        if lang == "te":
            if intent in ("tomorrow_forecast",) or (timeframe == "tomorrow" and intent == "current"):
                resp = f"రేపు {city}లో వాతావరణం {t_cond}గా ఉండే అవకాశం ఉంది. గరిష్ట ఉష్ణోగ్రత {t_temp_max}°C, కనిష్ట ఉష్ణోగ్రత {t_temp_min}°C నమోదు కావచ్చు. వర్షం పడే అవకాశం {t_rain_prob}%."
                followups = [f"{city}లో రేపు వర్షం పడుతుందా?", f"{city}లో ప్రస్తుత ఉష్ణోగ్రత ఎంత?", f"7 రోజుల వాతావరణ సూచన"]

            elif intent == "rain_check" or intent == "rain_probability":
                target_prob = t_rain_prob if timeframe == "tomorrow" else rain_prob
                period_str = "రేపు" if timeframe == "tomorrow" else "నేడు"
                if target_prob >= 50:
                    resp = f"{period_str} {city}లో వర్షం పడే అవకాశం చాలా ఎక్కువగా ఉంది ({target_prob}%). అవసరమైతే గొడుగు వెంట ఉంచుకోండి."
                elif target_prob >= 25:
                    resp = f"{period_str} {city}లో తేలికపాటి జల్లులు పడే అవకాశం ఉంది (వర్ష సూచన: {target_prob}%)."
                else:
                    resp = f"{period_str} {city}లో వర్షం పడే అవకాశం చాలా తక్కువగా ఉంది (కేవలం {target_prob}%). వాతావరణం పొడిగా ఉండే అవకాశం ఉంది."
                followups = [f"నేను గొడుగు తీసుకెళ్లాలా?", f"{city}లో ఉష్ణోగ్రత ఎంత?", f"గాలి వేగం ఎంత?"]

            elif intent == "umbrella":
                target_prob = t_rain_prob if timeframe == "tomorrow" else rain_prob
                if is_active_rain_or_storm or target_prob >= 40:
                    resp = f"అవును! {city}లో గొడుగు వెంట తీసుకెళ్లడం మంచిది. వర్షం పడే అవకాశం {target_prob}%గా ఉంది (ప్రస్తుత స్థితి: {cond})."
                else:
                    resp = f"{city}లో ప్రస్తుతానికి గొడుగు అవసరం లేదు. వర్ష సూచన కేవలం {target_prob}% మాత్రమే ఉంది."
                followups = [f"రేపు వర్షం పడుతుందా?", f"{city}లో ఉష్ణోగ్రత ఎంత?", f"ప్రయాణాలకు సురక్షితమేనా?"]

            elif intent == "temperature":
                if timeframe == "tomorrow":
                    resp = f"రేపు {city}లో ఉష్ణోగ్రత గరిష్టంగా {t_temp_max}°C, కనిష్టంగా {t_temp_min}°C నమోదవుతుంది."
                else:
                    resp = f"{city}లో ప్రస్తుత ఉష్ణోగ్రత {temp}°C (అనిపించే ఉష్ణోగ్రత: {feels_like}°C) మరియు వాతావరణం {cond}గా ఉంది."
                followups = [f"రేపు {city}లో ఉష్ణోగ్రత ఎంత?", f"వర్షం పడే అవకాశం ఎంత?", f"తేమ శాతం ఎంత?"]

            elif intent == "wind":
                resp = f"{city}లో ప్రస్తుత గాలి వేగం {wind} కి.మీ/గం ({wind_compass} దిశ), వాతావరణ పీడనం {pressure} hPa."
                followups = [f"{city}లో ఉష్ణోగ్రత ఎంత?", f"తుఫాను హెచ్చరికలు ఉన్నాయా?"]

            elif intent == "humidity":
                resp = f"{city}లో సాపేక్ష తేమ {humidity}%. ప్రస్తుత ఉష్ణోగ్రత {temp}°C (అనిపించే ఉష్ణోగ్రత: {feels_like}°C)."
                followups = [f"వర్షం పడుతుందా?", f"నేను గొడుగు తీసుకెళ్లాలా?"]

            elif intent == "sunrise_sunset":
                resp = f"{city}లో సూర్యోదయం సమయం {sunrise}, మరియు సూర్యాస్తమయం సమయం {sunset}."
                followups = [f"{city}లో నేటి ఉష్ణోగ్రత ఎంత?", f"రేపటి వాతావరణం ఎలా ఉంటుంది?"]

            elif intent == "hourly":
                h_lines = []
                for h in hourly[:5]:
                    h_lines.append(f"{h.get('hour_label')}: {h.get('temperature')}°C, {h.get('condition')} ({h.get('rain_probability')}% వర్షం)")
                resp = f"{city} రాబోయే గంటల వాతావరణ వివరాలు:\n" + "\n".join(f"• {l}" for l in h_lines)
                followups = [f"రేపటి సూచన", f"గొడుగు అవసరమా?"]

            elif intent == "forecast_7d":
                d_lines = []
                for d in daily[:5]:
                    d_lines.append(f"{d.get('day_name')}: {d.get('temp_max')}°C / {d.get('temp_min')}°C ({d.get('condition')}, {d.get('rain_probability')}% వర్షం)")
                resp = f"{city} రాబోయే రోజుల వాతావరణ సూచన:\n" + "\n".join(f"• {l}" for l in d_lines)
                followups = [f"రేపు వర్షం పడుతుందా?", f"వ్యవసాయ సూచనలు ఏమిటి?"]

            elif intent == "alerts":
                if has_alerts:
                    alerts_text = [a["title"] + " - " + a["description"] for a in alerts.get("official_alerts", [])] or [a["title"] for a in alerts.get("ai_advisory_alerts", [])]
                    resp = f"⚠️ {city} వాతావరణ హెచ్చరికలు:\n" + "\n".join(f"• {t}" for t in alerts_text)
                elif cape >= 1000 or humidity >= 75:
                    resp = f"{city}లో ప్రస్తుతం ఎటువంటి తీవ్ర తుఫాను లేదా వరద హెచ్చరికలు లేవు. వాతావరణం ఉక్కపోతతో కూడిన తేమగా ఉంది (తేమ: {humidity}%, CAPE: {cape} J/kg)."
                else:
                    resp = f"ప్రస్తుతం {city}లో ఎటువంటి తీవ్ర వాతావరణ హెచ్చరికలు లేవు. వాతావరణం సాధారణంగా ఉంది ({cond}, {temp}°C)."
                followups = [f"ప్రయాణాలకు సురక్షితమేనా?", f"వర్ష సూచన ఎంత?"]

            elif intent == "travel_safety":
                if has_alerts or (is_active_rain_or_storm and wind >= 30):
                    resp = f"{city}లో ప్రయాణాల సమయంలో అప్రమత్తంగా ఉండండి. వాతావరణం: {cond}, గాలి వేగం: {wind} కి.మీ/గం."
                else:
                    resp = f"{city}లో నేడు ప్రయాణాలకు వాతావరణం అనుకూలంగా మరియు సురక్షితంగా ఉంది! ఉష్ణోగ్రత {temp}°C, గాలి వేగం {wind} కి.మీ/గం."
                followups = [f"వర్షం పడే అవకాశం ఎంత?", f"వాతావరణ హెచ్చరికలు ఉన్నాయా?"]

            elif intent == "agriculture":
                agri_msg = advisories.get("agriculture", {}).get("primary_message", "వాతావరణ పరిస్థితులకు అనుగుణంగా వ్యవసాయ పనులు నిర్వహించండి.")
                resp = f"{city} రైతులకు సలహా: {agri_msg} (ప్రస్తుత ఉష్ణోగ్రత: {temp}°C, తేమ: {humidity}%, వర్ష సూచన: {rain_prob}%)."
                followups = [f"రేపు వర్షం పడుతుందా?", f"7 రోజుల వాతావరణం"]

            else:
                resp = f"{city}లో ప్రస్తుత వాతావరణం {cond}గా ఉంది. ఉష్ణోగ్రత {temp}°C (అనిపించే ఉష్ణోగ్రత: {feels_like}°C), తేమ {humidity}%, గాలి వేగం {wind} కి.మీ/గం మరియు వర్షం పడే అవకాశం {rain_prob}%."
                followups = [f"రేపు {city}లో వాతావరణం ఎలా ఉంటుంది?", f"గొడుగు తీసుకెళ్లాలా?", f"7 రోజుల సూచన"]

        # ----------------------------------------------------------------------
        # HINDI (hi) Grounded Responses
        # ----------------------------------------------------------------------
        elif lang == "hi":
            if intent in ("tomorrow_forecast",) or (timeframe == "tomorrow" and intent == "current"):
                resp = f"कल {city} में मौसम {t_cond} रहने की संभावना है। अधिकतम तापमान {t_temp_max}°C और न्यूनतम तापमान {t_temp_min}°C रहेगा। बारिश की संभावना {t_rain_prob}% है।"
                followups = [f"क्या कल {city} में बारिश होगी?", f"{city} में आज का तापमान क्या है?", f"7 दिनों का पूर्वानुमान"]

            elif intent == "rain_check" or intent == "rain_probability":
                target_prob = t_rain_prob if timeframe == "tomorrow" else rain_prob
                period_str = "कल" if timeframe == "tomorrow" else "आज"
                if target_prob >= 50:
                    resp = f"{period_str} {city} में बारिश की संभावना बहुत अधिक ({target_prob}%) है। छतरी साथ रखना उचित रहेगा।"
                elif target_prob >= 25:
                    resp = f"{period_str} {city} में हल्की फुहारों की संभावना है (बारिश की संभावना: {target_prob}%)।"
                else:
                    resp = f"{period_str} {city} में बारिश की संभावना नगण्य है (केवल {target_prob}%)। मौसम शुष्क रहेगा।"
                followups = [f"क्या छतरी ले जाना चाहिए?", f"{city} का तापमान क्या है?"]

            elif intent == "umbrella":
                target_prob = t_rain_prob if timeframe == "tomorrow" else rain_prob
                if is_active_rain_or_storm or target_prob >= 40:
                    resp = f"हाँ, {city} में छतरी साथ रखना बेहतर होगा! बारिश की संभावना {target_prob}% है और मौसम {cond} बना हुआ है।"
                else:
                    resp = f"{city} में अभी छतरी की आवश्यकता नहीं है। बारिश की संभावना केवल {target_prob}% है।"
                followups = [f"क्या कल बारिश होगी?", f"{city} में हवा की गति क्या है?"]

            elif intent == "temperature":
                if timeframe == "tomorrow":
                    resp = f"कल {city} में अधिकतम तापमान {t_temp_max}°C तथा न्यूनतम तापमान {t_temp_min}°C रहने का अनुमान है।"
                else:
                    resp = f"{city} में वर्तमान तापमान {temp}°C (महसूस: {feels_like}°C) है तथा मौसम {cond} है।"
                followups = [f"कल का मौसम कैसा रहेगा?", f"नमी कितनी है?"]

            elif intent == "wind":
                resp = f"{city} में हवा की गति {wind} किमी/घंटा ({wind_compass} दिशा) और वायुमंडलीय दबाव {pressure} hPa है।"
                followups = [f"क्या कोई तूफान की चेतावनी है?", f"{city} का तापमान क्या है?"]

            elif intent == "humidity":
                resp = f"{city} में सापेक्ष आर्द्रता (नमी) {humidity}% है। परिवेश का तापमान {temp}°C (महसूस: {feels_like}°C) है।"
                followups = [f"क्या बारिश होगी?", f"क्या छतरी ले जानी चाहिए?"]

            elif intent == "sunrise_sunset":
                resp = f"{city} में सूर्योदय {sunrise} और सूर्यास्त {sunset} पर होगा।"
                followups = [f"आज का तापमान क्या है?", f"कल का पूर्वानुमान"]

            elif intent == "hourly":
                h_lines = [f"{h.get('hour_label')}: {h.get('temperature')}°C, {h.get('condition')} ({h.get('rain_probability')}% बारिश)" for h in hourly[:5]]
                resp = f"{city} में अगले कुछ घंटों का मौसम:\n" + "\n".join(f"• {l}" for l in h_lines)
                followups = [f"कल का पूर्वानुमान", f"बारिश की संभावना"]

            elif intent == "forecast_7d":
                d_lines = [f"{d.get('day_name')}: {d.get('temp_max')}°C / {d.get('temp_min')}°C ({d.get('condition')}, {d.get('rain_probability')}% बारिश)" for d in daily[:5]]
                resp = f"{city} के लिए आगामी दिनों का मौसम पूर्वानुमान:\n" + "\n".join(f"• {l}" for l in d_lines)
                followups = [f"क्या कल बारिश होगी?", f"किसानों के लिए सलाह"]

            elif intent == "alerts":
                if has_alerts:
                    alert_texts = [a["title"] + " - " + a["description"] for a in alerts.get("official_alerts", [])] or [a["title"] for a in alerts.get("ai_advisory_alerts", [])]
                    resp = f"⚠️ {city} के लिए मौसम चेतावनी:\n" + "\n".join(f"• {t}" for t in alert_texts)
                elif cape >= 1000 or humidity >= 75:
                    resp = f"{city} में फिलहाल कोई गंभीर तूफान चेतावनी नहीं है। वातावरण अत्यधिक नम एवं उमस भरा है (नमी: {humidity}%, CAPE: {cape} J/kg)।"
                else:
                    resp = f"वर्तमान में {city} के लिए कोई गंभीर मौसम चेतावनी नहीं है। मौसम सामान्य है ({cond}, {temp}°C)।"
                followups = [f"क्या यात्रा के लिए सुरक्षित है?", f"बारिश की संभावना"]

            elif intent == "travel_safety":
                if has_alerts or (is_active_rain_or_storm and wind >= 30):
                    resp = f"{city} में यात्रा के दौरान सावधानी बरतें। मौसम: {cond}, हवा की गति: {wind} किमी/घंटा।"
                else:
                    resp = f"{city} में आज यात्रा के लिए मौसम पूरी तरह अनुकूल और सुरक्षित है! तापमान {temp}°C और हवा {wind} किमी/घंटा है।"
                followups = [f"बारिश की संभावना क्या है?", f"मौसम चेतावनी"]

            elif intent == "agriculture":
                agri_msg = advisories.get("agriculture", {}).get("primary_message", "मौसम की स्थिति के अनुसार सिंचाई की योजना बनाएं।")
                resp = f"{city} के किसानों के लिए सलाह: {agri_msg} (वर्तमान तापमान: {temp}°C, नमी: {humidity}%, बारिश: {rain_prob}%)।"
                followups = [f"क्या कल बारिश होगी?", f"7 दिनों का पूर्वानुमान"]

            else:
                resp = f"{city} में वर्तमान तापमान {temp}°C (महसूस: {feels_like}°C) है। मौसम {cond} है, नमी {humidity}%, हवा की गति {wind} किमी/घंटा और बारिश की संभावना {rain_prob}% है।"
                followups = [f"कल {city} में मौसम कैसा रहेगा?", f"क्या छतरी ले जानी चाहिए?", f"7 दिनों का पूर्वानुमान"]

        # ----------------------------------------------------------------------
        # TAMIL (ta) Grounded Responses
        # ----------------------------------------------------------------------
        elif lang == "ta":
            if intent in ("tomorrow_forecast",) or (timeframe == "tomorrow" and intent == "current"):
                resp = f"நாளை {city}ல் வானிலை {t_cond} ஆக இருக்கும் என எதிர்பார்க்கப்படுகிறது. அதிகபட்ச வெப்பநிலை {t_temp_max}°C, குறைந்தபட்ச வெப்பநிலை {t_temp_min}°C. மழை வாய்ப்பு {t_rain_prob}%."
                followups = [f"நாளை {city}ல் மழை பெய்யுமா?", f"{city} தற்போதைய வெப்பநிலை", f"7 நாள் வானிலை"]
            elif intent in ("rain_check", "rain_probability"):
                target_prob = t_rain_prob if timeframe == "tomorrow" else rain_prob
                period_str = "நாளை" if timeframe == "tomorrow" else "இன்று"
                resp = f"{period_str} {city}ல் மழை பெய்ய {target_prob}% வாய்ப்புள்ளது."
                followups = [f"குடை தேவையா?", f"வெப்பநிலை என்ன?"]
            elif intent == "umbrella":
                target_prob = t_rain_prob if timeframe == "tomorrow" else rain_prob
                resp = f"ஆம், {city}ல் குடை எடுத்துச் செல்வது நல்லது! மழை வாய்ப்பு {target_prob}%." if target_prob >= 40 else f"{city}ல் தற்போது குடை தேவையில்லை. மழை வாய்ப்பு {target_prob}% மட்டுமே."
                followups = [f"நாளை வானிலை எப்படி இருக்கும்?", f"வெப்பநிலை என்ன?"]
            elif intent == "temperature":
                resp = f"நாளை {city}ல் வெப்பநிலை {t_temp_max}°C / {t_temp_min}°C ஆக இருக்கும்." if timeframe == "tomorrow" else f"{city}ல் தற்போதைய வெப்பநிலை {temp}°C ({cond})."
                followups = [f"மழை பெய்யுமா?", f"ஈரப்பதம் எவ்வளவு?"]
            else:
                resp = f"{city}ல் தற்போதைய வெப்பநிலை {temp}°C ({cond}). ஈரப்பதம் {humidity}%, காற்றின் வேகம் {wind} கி.மீ/மணி, மழை வாய்ப்பு {rain_prob}%."
                followups = [f"நாளை {city}ல் வானிலை எப்படி?", f"7 நாள் முன்னறிவிப்பு"]

        # ----------------------------------------------------------------------
        # MALAYALAM (ml) Grounded Responses
        # ----------------------------------------------------------------------
        elif lang == "ml":
            if intent in ("tomorrow_forecast",) or (timeframe == "tomorrow" and intent == "current"):
                resp = f"നാളെ {city}യിൽ കാലാവസ്ഥ {t_cond} ആയിരിക്കും. പരമാവധി താപനില {t_temp_max}°C, കുറഞ്ഞ താപനില {t_temp_min}°C. മഴ സാധ്യത {t_rain_prob}%."
                followups = [f"നാളെ {city}യിൽ മഴ പെയ്യുമോ?", f"ഇന്നത്തെ താപനില", f"7 ദിവസത്തെ പ്രവചനം"]
            elif intent in ("rain_check", "rain_probability"):
                target_prob = t_rain_prob if timeframe == "tomorrow" else rain_prob
                period_str = "നാളെ" if timeframe == "tomorrow" else "ഇന്ന്"
                resp = f"{period_str} {city}യിൽ മഴ പെയ്യാൻ {target_prob}% സാധ്യതയുണ്ട്."
                followups = [f"കുട എടുക്കണോ?", f"നിലവിലെ താപനില എത്ര?"]
            elif intent == "umbrella":
                target_prob = t_rain_prob if timeframe == "tomorrow" else rain_prob
                resp = f"അതെ, {city}യിൽ കുട കരുതുന്നത് നന്നായിരിക്കും! മഴ സാധ്യത {target_prob}%." if target_prob >= 40 else f"{city}യിൽ ഇപ്പോൾ കുടയുടെ ആവശ്യമില്ല. മഴ സാധ്യത {target_prob}% മാത്രമാണ്."
                followups = [f"നാളെ മഴ പെയ്യുമോ?", f"കാറ്റിന്റെ വേഗത എത്ര?"]
            elif intent == "temperature":
                resp = f"നാളെ {city}യിൽ താപനില {t_temp_max}°C / {t_temp_min}°C ആയിരിക്കും." if timeframe == "tomorrow" else f"{city}യിൽ നിലവിലെ താപനില {temp}°C ആണ് ({cond})."
                followups = [f"മഴ പെയ്യാൻ സാധ്യതയുണ്ടോ?", f"ഈർപ്പം എത്ര?"]
            else:
                resp = f"{city}യിൽ നിലവിലെ താപനില {temp}°C ({cond}) ആണ്. ഈർപ്പം {humidity}%, കാറ്റിന്റെ വേഗത {wind} കി.മീ/മണിക്കൂർ, മഴ സാധ്യത {rain_prob}%."
                followups = [f"നാളെ {city}യിൽ കാലാവസ്ഥ എങ്ങനെ?", f"7 ദിവസത്തെ പ്രവചനം"]

        # ----------------------------------------------------------------------
        # ENGLISH (en) Grounded Responses
        # ----------------------------------------------------------------------
        else:
            if intent in ("tomorrow_forecast",) or (timeframe == "tomorrow" and intent == "current"):
                resp = (
                    f"Tomorrow in {city}, expected conditions are {t_cond} with a daytime high of {t_temp_max}°C "
                    f"and an overnight low of {t_temp_min}°C. Precipitation probability is {t_rain_prob}%. "
                    f"Sunrise will be at {t_sunrise} and sunset at {t_sunset}."
                )
                followups = [f"Will it rain tomorrow in {city}?", f"What is the current temperature in {city}?", f"7-day forecast for {city}"]

            elif intent == "rain_check" or intent == "rain_probability":
                target_prob = t_rain_prob if timeframe == "tomorrow" else rain_prob
                period_str = "Tomorrow" if timeframe == "tomorrow" else "Today"
                cond_str = t_cond if timeframe == "tomorrow" else cond
                if target_prob >= 60:
                    resp = f"{period_str} in {city}, rain is highly likely with a {target_prob}% chance of precipitation ({cond_str.lower()})."
                elif target_prob >= 30:
                    resp = f"{period_str} in {city}, there is a moderate {target_prob}% chance of scattered rain or showers ({cond_str.lower()})."
                else:
                    resp = f"Rain is unlikely {period_str.lower()} in {city}. Precipitation probability is low at {target_prob}% with {cond_str.lower()} conditions."
                followups = [f"Should I carry an umbrella?", f"What is tomorrow's forecast?", f"Is it safe to travel today?"]

            elif intent == "umbrella":
                target_prob = t_rain_prob if timeframe == "tomorrow" else rain_prob
                period_str = "tomorrow" if timeframe == "tomorrow" else "today"
                if is_active_rain_or_storm or target_prob >= 40:
                    resp = f"Yes, carry an umbrella in {city} {period_str}! Precipitation chance is {target_prob}% with {cond.lower()} conditions."
                elif cape >= 1000 or humidity >= 75:
                    resp = f"No umbrella is strictly needed right now in {city}. Conditions are Hot/Humid with convective potential (Humidity: {humidity}%, Precip: {precip} mm), but no active storm is in progress."
                else:
                    resp = f"No umbrella is strictly needed right now in {city}. Rain probability is low at {target_prob}%, and current conditions are {cond.lower()}."
                followups = [f"Will it rain tomorrow in {city}?", f"What is the wind speed?", f"7-day forecast for {city}"]

            elif intent == "temperature":
                if timeframe == "tomorrow":
                    resp = f"Tomorrow in {city}, temperatures are forecast to reach a high of {t_temp_max}°C and a low of {t_temp_min}°C ({t_cond.lower()})."
                else:
                    resp = f"The current temperature in {city} is {temp}°C (feels like {feels_like}°C) with {cond.lower()} conditions."
                followups = [f"Will it rain today in {city}?", f"What is the forecast for tomorrow?", f"Humidity in {city}"]

            elif intent == "wind":
                resp = f"The wind speed in {city} is currently {wind} km/h blowing from the {wind_compass}, with atmospheric pressure at {pressure} hPa."
                followups = [f"Is there a storm alert for {city}?", f"What is the temperature?"]

            elif intent == "humidity":
                resp = f"The relative humidity in {city} is currently {humidity}%. The ambient temperature is {temp}°C (feels like {feels_like}°C)."
                followups = [f"Will it rain today?", f"Should I carry an umbrella?"]

            elif intent == "sunrise_sunset":
                resp = f"In {city}, sunrise is at {sunrise} and sunset is at {sunset}."
                followups = [f"What is the temperature today in {city}?", f"Forecast for tomorrow"]

            elif intent == "hourly":
                h_lines = [f"{h.get('hour_label')}: {h.get('temperature')}°C, {h.get('condition')} ({h.get('rain_probability')}% rain)" for h in hourly[:6]]
                resp = f"Here is the hourly forecast for {city} over the next few hours:\n" + "\n".join(f"• {l}" for l in h_lines)
                followups = [f"Tomorrow's forecast for {city}", f"Will it rain later today?"]

            elif intent == "forecast_7d":
                day_summaries = []
                for d in daily[:5]:
                    day_summaries.append(f"{d.get('day_name')}: {d.get('temp_max')}°C / {d.get('temp_min')}°C ({d.get('condition')}, {d.get('rain_probability')}% rain)")
                resp = f"Here is the upcoming 5-day forecast for {city}:\n" + "\n".join(f"• {s}" for s in day_summaries)
                followups = [f"Will it rain on the weekend?", f"Should I carry an umbrella?", f"Farming advice for the week"]

            elif intent == "alerts":
                if has_alerts:
                    alert_texts = [a["title"] + " - " + a["description"] for a in alerts.get("official_alerts", [])]
                    if not alert_texts:
                        alert_texts = [a["title"] + " - " + a["description"] for a in alerts.get("ai_advisory_alerts", [])]
                    resp = f"Active Weather Alerts for {city}:\n" + "\n".join(f"⚠️ {t}" for t in alert_texts)
                elif cape >= 1000 or humidity >= 75:
                    resp = f"No severe storm warning for {city}. Atmosphere is Hot/Humid with convective potential (Humidity: {humidity}%, CAPE: {cape} J/kg, Precip: {precip} mm), but no active storm is detected."
                else:
                    resp = f"Good news! There are currently no severe weather warnings or cyclone alerts for {city}. Conditions are {cond.lower()} at {temp}°C."
                followups = [f"Is it safe to travel?", f"What is the rain forecast?", f"Wind speed in {city}"]

            elif intent == "travel_safety":
                if has_alerts or (is_active_rain_or_storm and (rain_prob >= 70 or wind >= 35)):
                    resp = f"Travel with caution in {city}. Weather conditions: {cond}, wind speed {wind} km/h, and active precipitation {precip} mm. Please allow extra transit time."
                elif cape >= 1000 or humidity >= 75:
                    resp = f"It is safe for travel in {city}! The weather is Hot/Humid with convective potential (Temperature: {temp}°C, Humidity: {humidity}%), but there is no active storm."
                else:
                    resp = f"It is generally safe for travel in {city} today! Conditions are {cond.lower()} with moderate winds of {wind} km/h and temperature at {temp}°C."
                followups = [f"What is the rain probability?", f"Any weather warnings for {city}?", f"Forecast for tomorrow"]

            elif intent == "agriculture":
                agri_msg = advisories.get("agriculture", {}).get("primary_message", "Proceed with normal seasonal agricultural operations.")
                resp = f"Farming advisory for {city}: {agri_msg} (Current: {temp}°C, Humidity: {humidity}%, Precip: {precip} mm, Rain Chance: {rain_prob}%)."
                followups = [f"Should I irrigate crops today?", f"Will it rain tomorrow?", f"7-day weather forecast"]

            else:
                resp = (
                    f"In {city}, the weather is currently {cond.lower()} at {temp}°C (feels like {feels_like}°C). "
                    f"Humidity is {humidity}%, wind speed is {wind} km/h ({wind_compass}), and rain probability is {rain_prob}%."
                )
                followups = [f"Will it rain tomorrow in {city}?", f"Should I carry an umbrella today?", f"7-day forecast for {city}"]

        return resp, followups

    async def chat(
        self,
        message: str,
        city_override: Optional[str] = None,
        lat_override: Optional[float] = None,
        lon_override: Optional[float] = None,
        language: str = "en",
        session_id: str = "default-session",
        force_demo: bool = False
    ) -> Dict[str, Any]:
        """
        Grounded WeatherGPT Chatbot Engine:
        1. Understand language & user intent
        2. Resolve location using query, conversational memory, or frontend context
        3. Query real-time Weather API
        4. Interpret via Gemini (or Grounded Rule Engine fallback)
        5. Return grounded response with live data metadata
        """
        # 1. Determine Language
        target_lang = self.detect_language(message, fallback_lang=language)

        # 2. Retrieve / initialize session memory
        session = self.sessions.setdefault(session_id, {
            "last_city": None,
            "last_lat": None,
            "last_lon": None,
            "last_timeframe": "current",
            "last_intent": "current",
            "history": []
        })

        # 3. Location Extraction with Session Context Memory
        extracted_city = self.extract_location(message)
        if extracted_city:
            target_city = extracted_city
        elif session.get("last_city"):
            target_city = session["last_city"]
        elif city_override and city_override.strip() and city_override.strip() != "Visakhapatnam":
            target_city = city_override.strip()
        elif city_override and city_override.strip() == "Visakhapatnam" and lat_override is not None and abs(lat_override - 17.6801) < 0.001:
            # Explicitly selected Visakhapatnam on dashboard
            target_city = city_override.strip()
        elif lat_override is not None and lon_override is not None and (lat_override != 0.0 or lon_override != 0.0):
            # GPS location without explicit city name
            target_city = city_override or "Detected Location"
        else:
            # City is truly missing and cannot be inferred!
            # Prompt user politely without assuming a random location
            ask_msg = self._get_missing_location_response(target_lang)
            return {
                "response": ask_msg,
                "detected_intent": "location_clarification",
                "location_used": "Unknown",
                "language": target_lang,
                "weather_summary": None,
                "suggested_followups": [
                    "Weather in Visakhapatnam",
                    "Weather in Hyderabad",
                    "Weather in Delhi",
                    "Weather in Mumbai"
                ],
                "is_demo": False,
                "is_live": True,
                "timeframe": "current"
            }

        # 4. Detect Intent & Timeframe
        intent = self.detect_intent(
            message,
            previous_intent=session.get("last_intent")
        )
        timeframe = self.detect_timeframe(
            message,
            previous_timeframe=session.get("last_timeframe")
        )

        # 5. Resolve Coordinates
        lat, lon, resolved_city = await weather_service.resolve_coordinates_async(
            target_city,
            lat=lat_override if target_city == city_override else None,
            lon=lon_override if target_city == city_override else None
        )

        if lat is None or lon is None:
            # City geocoding failed
            err_msg = (
                f"Could not find live weather data for '{target_city}'. "
                f"Please check the spelling or specify another city name."
            )
            return {
                "response": err_msg,
                "detected_intent": intent,
                "location_used": target_city,
                "language": target_lang,
                "weather_summary": None,
                "suggested_followups": ["Weather in Visakhapatnam", "Weather in Hyderabad", "Weather in Delhi"],
                "is_demo": False,
                "is_live": False,
                "timeframe": timeframe
            }

        # Update session memory location
        session["last_city"] = resolved_city
        session["last_lat"] = lat
        session["last_lon"] = lon
        session["last_intent"] = intent
        session["last_timeframe"] = timeframe

        # 6. Fetch live meteorological context
        try:
            context = await weather_service.get_chat_context(
                lat, lon, resolved_city, language=target_lang, force_demo=force_demo
            )
        except Exception as e:
            err_str = str(e).lower()
            logger.error(f"Chat weather retrieval failed for {resolved_city}: {e}")
            if "offline" in err_str or "connection" in err_str or "name resolution" in err_str:
                error_response = "You are offline. Live weather data is currently unavailable. Please check your internet connection and try again."
            else:
                error_response = "Live weather data is temporarily unavailable. Please try again in a moment."

            return {
                "response": error_response,
                "detected_intent": intent,
                "location_used": resolved_city,
                "language": target_lang,
                "weather_summary": None,
                "suggested_followups": [f"Retry live weather for {resolved_city}"],
                "is_demo": False,
                "is_live": False,
                "timeframe": timeframe
            }

        cur = context["current"]
        daily = context["daily"]
        hourly = context["hourly"]
        alerts = context["alerts"]
        advisories = context["advisories"]

        weather_summary = {
            "temp": cur.get("temperature"),
            "feels_like": cur.get("feels_like"),
            "condition": cur.get("condition"),
            "rain_prob": cur.get("rain_probability"),
            "humidity": cur.get("humidity"),
            "wind_speed": cur.get("wind_speed"),
            "wind_compass": cur.get("wind_compass"),
            "precipitation": cur.get("precipitation"),
            "sunrise": cur.get("sunrise"),
            "sunset": cur.get("sunset")
        }

        # 7. Gemini Reasoning Layer (Grounded on live data)
        if self._gemini_client and not force_demo:
            try:
                system_prompt = f"""You are WeatherGPT, an expert AI meteorologist and conversational weather assistant participating in Smart India Hackathon (SIH).

CRITICAL DIRECTIVES:
1. Ground every answer STRICTLY on the real live meteorological data provided below for {resolved_city}.
2. You MUST NEVER hallucinate or guess weather values.
3. Severe Weather Warning Directive: Do NOT state an active storm, severe thunderstorm, or heavy rain warning unless precipitation > 1.0mm OR WMO weather code is between 80 and 99. If CAPE >= 1000 or humidity >= 75 with low precipitation, report as 'Hot/Humid with convective potential' but NOT an active storm.
4. If asked in language '{target_lang}', respond fluently, naturally, and warmly in that language (en, hi, te, ta, ml).
5. If the user asks about tomorrow, use the tomorrow metrics provided.
6. If the user asks about rain probability, provide the exact percentage.

LIVE METEOROLOGICAL OBSERVATION FOR {resolved_city} ({lat}, {lon}):
- Current Temperature: {cur.get('temperature')}°C (Feels like: {cur.get('feels_like')}°C)
- Current Condition: {cur.get('condition')} (WMO Code: {cur.get('weather_code')})
- Precipitation: {cur.get('precipitation', 0.0)} mm
- CAPE: {cur.get('cape', 0.0)} J/kg
- Relative Humidity: {cur.get('humidity')}%
- Wind: {cur.get('wind_speed')} km/h ({cur.get('wind_compass')})
- Rain Probability Today: {cur.get('rain_probability')}%
- Sunrise: {cur.get('sunrise')} | Sunset: {cur.get('sunset')}
- Tomorrow Forecast: High {daily[1].get('temp_max') if len(daily)>1 else 'N/A'}°C, Low {daily[1].get('temp_min') if len(daily)>1 else 'N/A'}°C, Condition: {daily[1].get('condition') if len(daily)>1 else 'N/A'}, Rain Chance: {daily[1].get('rain_probability') if len(daily)>1 else 'N/A'}%
- Active Alerts: {alerts.get('official_alerts')}
- AI Advisories: {advisories}"""

                response = self._gemini_client.models.generate_content(
                    model=self.model_name,
                    contents=f"User Query: {message}\n\nRespond strictly grounded in the real meteorological data provided.",
                    config={"system_instruction": system_prompt}
                )
                if response and response.text:
                    bot_text = response.text.strip()
                    followups = [
                        f"Will it rain tomorrow in {resolved_city}?",
                        f"What is the wind speed in {resolved_city}?",
                        f"7-day forecast for {resolved_city}"
                    ]
                    # Update session history
                    session["history"].append({"user": message, "bot": bot_text})
                    return {
                        "response": bot_text,
                        "detected_intent": intent,
                        "location_used": resolved_city,
                        "language": target_lang,
                        "weather_summary": weather_summary,
                        "suggested_followups": followups,
                        "is_demo": cur.get("is_demo", False),
                        "is_live": not cur.get("is_demo", False),
                        "timeframe": timeframe
                    }
            except Exception as e:
                logger.warning(f"Gemini API dynamic reasoning bypassed: {e}. Falling back to Grounded Rule Engine.")

        # 8. High-Quality Grounded Rule Engine Fallback (Zero downtime, Zero hallucination)
        answer, followups = self._generate_grounded_fallback(
            intent, timeframe, resolved_city, context, target_lang
        )

        session["history"].append({"user": message, "bot": answer})

        return {
            "response": answer,
            "detected_intent": intent,
            "location_used": resolved_city,
            "language": target_lang,
            "weather_summary": weather_summary,
            "suggested_followups": followups,
            "is_demo": cur.get("is_demo", False),
            "is_live": not cur.get("is_demo", False),
            "timeframe": timeframe
        }

llm_service = LLMService()
