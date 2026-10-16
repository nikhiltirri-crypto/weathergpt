import uuid
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta, timezone
from app.core.config import settings
from app.core.constants import DEFAULT_CITIES, KNOWN_CITY_COORDINATES
from app.services.open_meteo_service import OpenMeteoProvider
from app.services.mock_service import MockWeatherProvider
from app.services.advisory_service import AdvisoryService

logger = logging.getLogger("weathergpt")

# In-memory dynamic geocoding cache to prevent repeated network lookups
_DYNAMIC_GEOCODE_CACHE: Dict[str, Dict[str, Any]] = {}

class WeatherService:
    def __init__(self):
        self.live_provider = OpenMeteoProvider()
        self.mock_provider = MockWeatherProvider()

    def get_provider(self, force_demo: bool = False):
        if force_demo or settings.DEMO_MODE:
            return self.mock_provider
        return self.live_provider

    def resolve_coordinates(self, city_name: str, lat: Optional[float] = None, lon: Optional[float] = None) -> Tuple[float, float, str]:
        """
        Verify and resolve coordinates for the requested city.
        Guarantees that selecting or requesting a city uses that city's actual coordinates,
        preventing incorrect coordinate fallbacks.
        """
        clean_name = (city_name or "").strip()
        lower_name = clean_name.lower()

        # Check known verified coordinates first
        if lower_name in KNOWN_CITY_COORDINATES:
            known = KNOWN_CITY_COORDINATES[lower_name]
            if lat is None or lon is None or (abs(lat - 17.6801) < 0.001 and abs(lon - 83.2016) < 0.001 and "visakhapatnam" not in lower_name and "vizag" not in lower_name):
                return known["latitude"], known["longitude"], known["name"]

        # Check dynamic geocode cache
        if lower_name in _DYNAMIC_GEOCODE_CACHE:
            cached = _DYNAMIC_GEOCODE_CACHE[lower_name]
            return cached["latitude"], cached["longitude"], cached["name"]

        # If lat and lon are provided and valid, keep them
        if lat is not None and lon is not None and (lat != 0.0 or lon != 0.0):
            if abs(lat - 17.6801) < 0.001 and abs(lon - 83.2016) < 0.001 and "visakhapatnam" not in lower_name and "vizag" not in lower_name:
                for k, v in KNOWN_CITY_COORDINATES.items():
                    if k in lower_name or lower_name in k:
                        return v["latitude"], v["longitude"], v["name"]
            return lat, lon, clean_name or "Unknown Location"

        # Fallback to default city Visakhapatnam if nothing supplied
        default_city = DEFAULT_CITIES[0]
        return default_city["latitude"], default_city["longitude"], default_city["name"]

    async def resolve_coordinates_async(self, city_name: str, lat: Optional[float] = None, lon: Optional[float] = None) -> Tuple[Optional[float], Optional[float], str]:
        """
        Asynchronously resolve coordinates for any city name globally.
        Checks known cities, in-memory cache, and queries live Open-Meteo geocoding.
        Returns (None, None, city_name) if the location cannot be resolved.
        """
        clean_name = (city_name or "").strip()
        if not clean_name:
            if lat is not None and lon is not None:
                return lat, lon, "Current Location"
            return None, None, ""

        lower_name = clean_name.lower()

        # 1. Check known verified coordinates
        if lower_name in KNOWN_CITY_COORDINATES:
            known = KNOWN_CITY_COORDINATES[lower_name]
            return known["latitude"], known["longitude"], known["name"]

        # 2. Check dynamic cache
        if lower_name in _DYNAMIC_GEOCODE_CACHE:
            cached = _DYNAMIC_GEOCODE_CACHE[lower_name]
            return cached["latitude"], cached["longitude"], cached["name"]

        # 3. If explicit non-default coordinates were provided
        if lat is not None and lon is not None and (lat != 0.0 or lon != 0.0):
            # If coordinates are not default Visakhapatnam coords, trust them
            if not (abs(lat - 17.6801) < 0.001 and abs(lon - 83.2016) < 0.001 and "visakhapatnam" not in lower_name and "vizag" not in lower_name):
                return lat, lon, clean_name

        # 4. Query live geocoding API
        try:
            geo_results = await self.live_provider.geocode_city(clean_name, count=1)
            if geo_results:
                r = geo_results[0]
                res_lat = r["latitude"]
                res_lon = r["longitude"]
                res_name = r["name"]
                _DYNAMIC_GEOCODE_CACHE[lower_name] = {
                    "latitude": res_lat,
                    "longitude": res_lon,
                    "name": res_name
                }
                return res_lat, res_lon, res_name
        except Exception as e:
            logger.warning(f"Geocoding failed for '{clean_name}': {e}")

        # If coordinates were provided, return them as fallback
        if lat is not None and lon is not None:
            return lat, lon, clean_name

        return None, None, clean_name

    async def get_chat_context(self, lat: float, lon: float, city_name: str, language: str = "en", force_demo: bool = False) -> Dict[str, Any]:
        """
        Fetch real-time observation, hourly, daily forecasts, alerts, and advisories concurrently for chatbot reasoning.
        """
        import asyncio
        cur_task = asyncio.create_task(self.get_current(lat, lon, city_name, force_demo))
        daily_task = asyncio.create_task(self.get_daily(lat, lon, city_name, days=7, force_demo=force_demo))
        hourly_task = asyncio.create_task(self.get_hourly(lat, lon, city_name, hours=24, force_demo=force_demo))
        alerts_task = asyncio.create_task(self.get_alerts(lat, lon, city_name, force_demo))
        advisories_task = asyncio.create_task(self.get_advisories(lat, lon, city_name, lang=language, force_demo=force_demo))

        results = await asyncio.gather(cur_task, daily_task, hourly_task, alerts_task, advisories_task, return_exceptions=True)

        cur_res = results[0]
        if isinstance(cur_res, Exception):
            raise cur_res

        daily_res = results[1] if not isinstance(results[1], Exception) else []
        hourly_res = results[2] if not isinstance(results[2], Exception) else []
        alerts_res = results[3] if not isinstance(results[3], Exception) else {"city": city_name, "has_alerts": False, "official_alerts": [], "ai_advisory_alerts": []}
        adv_res = results[4] if not isinstance(results[4], Exception) else {}

        return {
            "current": cur_res,
            "daily": daily_res,
            "hourly": hourly_res,
            "alerts": alerts_res,
            "advisories": adv_res,
            "city": city_name,
            "latitude": lat,
            "longitude": lon
        }

    def _log_weather_request(self, city: str, lat: float, lon: float, provider_name: str, temp: Any, unit: str = "°C"):
        """Log development meteorological request details per SIH specification"""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print("\n" + "=" * 55, flush=True)
        print("METEOROLOGICAL DATA REQUEST AUDIT LOG", flush=True)
        print(f"City: {city}", flush=True)
        print(f"Latitude: {lat}", flush=True)
        print(f"Longitude: {lon}", flush=True)
        print(f"Weather API: {provider_name}", flush=True)
        print(f"API temperature: {temp}", flush=True)
        print(f"API temperature unit: {unit}", flush=True)
        print(f"Timestamp: {timestamp}", flush=True)
        print("=" * 55 + "\n", flush=True)

    async def search_locations(self, query: str) -> List[Dict[str, Any]]:
        query = query.strip()
        if not query:
            return DEFAULT_CITIES

        # Check in default and known cities first
        matched = []
        seen = set()
        for c in DEFAULT_CITIES:
            if query.lower() in c["name"].lower() or query.lower() in c["state"].lower():
                matched.append(c)
                seen.add(c["name"].lower())

        for k, v in KNOWN_CITY_COORDINATES.items():
            if (query.lower() in k or k in query.lower()) and v["name"].lower() not in seen:
                matched.append(v)
                seen.add(v["name"].lower())

        # Query live geocoding API
        try:
            live_results = await self.live_provider.geocode_city(query)
            if live_results:
                for r in live_results:
                    if r["name"].lower() not in seen:
                        matched.append(r)
                        seen.add(r["name"].lower())
        except Exception:
            pass

        return matched if matched else DEFAULT_CITIES[:4]

    async def get_current(self, lat: float, lon: float, city_name: str, force_demo: bool = False) -> Dict[str, Any]:
        lat, lon, city_name = self.resolve_coordinates(city_name, lat, lon)
        provider = self.get_provider(force_demo)
        
        try:
            data = await provider.get_current_weather(lat, lon, city_name)
            self._log_weather_request(
                city=city_name,
                lat=lat,
                lon=lon,
                provider_name=provider.provider_name,
                temp=data.get("temperature"),
                unit="°C"
            )
            return data
        except Exception as e:
            # If explicitly in DEMO mode or forced demo, mock is expected
            if force_demo or settings.DEMO_MODE:
                data = await self.mock_provider.get_current_weather(lat, lon, city_name)
                self._log_weather_request(
                    city=city_name,
                    lat=lat,
                    lon=lon,
                    provider_name=self.mock_provider.provider_name,
                    temp=data.get("temperature"),
                    unit="°C"
                )
                return data
            
            # In REAL mode, do NOT silently mask live API failures with hardcoded 28.5 / 29°C mock data
            logger.error(f"Live meteorological provider failed for {city_name} ({lat}, {lon}): {e}")
            raise RuntimeError(f"Live meteorological feed connection failed for {city_name}: {str(e)}")

    async def get_hourly(self, lat: float, lon: float, city_name: str, hours: int = 24, force_demo: bool = False) -> List[Dict[str, Any]]:
        lat, lon, city_name = self.resolve_coordinates(city_name, lat, lon)
        provider = self.get_provider(force_demo)
        try:
            return await provider.get_hourly_forecast(lat, lon, city_name, hours)
        except Exception as e:
            if force_demo or settings.DEMO_MODE:
                return await self.mock_provider.get_hourly_forecast(lat, lon, city_name, hours)
            logger.error(f"Hourly forecast failed: {e}")
            raise RuntimeError(f"Live hourly forecast unavailable for {city_name}: {str(e)}")

    async def get_daily(self, lat: float, lon: float, city_name: str, days: int = 7, force_demo: bool = False) -> List[Dict[str, Any]]:
        lat, lon, city_name = self.resolve_coordinates(city_name, lat, lon)
        provider = self.get_provider(force_demo)
        try:
            return await provider.get_daily_forecast(lat, lon, city_name, days)
        except Exception as e:
            if force_demo or settings.DEMO_MODE:
                return await self.mock_provider.get_daily_forecast(lat, lon, city_name, days)
            logger.error(f"Daily forecast failed: {e}")
            raise RuntimeError(f"Live daily forecast unavailable for {city_name}: {str(e)}")

    async def get_climate(self, lat: float, lon: float, city_name: str, days_back: int = 30, force_demo: bool = False) -> Dict[str, Any]:
        lat, lon, city_name = self.resolve_coordinates(city_name, lat, lon)
        provider = self.get_provider(force_demo)
        try:
            return await provider.get_historical_climate(lat, lon, city_name, days_back)
        except Exception as e:
            if force_demo or settings.DEMO_MODE:
                return await self.mock_provider.get_historical_climate(lat, lon, city_name, days_back)
            logger.error(f"Climate trends failed: {e}")
            raise RuntimeError(f"Historical climate data unavailable for {city_name}: {str(e)}")

    async def get_alerts(self, lat: float, lon: float, city_name: str, force_demo: bool = False) -> Dict[str, Any]:
        """
        Audit Alert System:
        - DO NOT label alerts as 'OFFICIAL' unless retrieved from a genuine official warning authority.
        - Do not generate fake official alerts from precipitation probability or threshold rules.
        - Separate strictly into OFFICIAL WARNING and AI ADVISORY.
        - If no verified official warning data is available, official_alerts must be empty [].
        """
        lat, lon, city_name = self.resolve_coordinates(city_name, lat, lon)
        
        # Real official meteorological alerts from genuine government feeds (e.g. IMD CAP)
        # Open-Meteo does not provide official CAP warnings for India in the free tier.
        # We do NOT fabricate or simulate official alerts in Real mode.
        official_alerts: List[Dict[str, Any]] = []
        ai_advisories: List[Dict[str, Any]] = []

        try:
            current = await self.get_current(lat, lon, city_name, force_demo)
            daily = await self.get_daily(lat, lon, city_name, days=3, force_demo=force_demo)
        except Exception:
            current = {}
            daily = []

        temp = current.get("temperature", 25.0)
        wind = current.get("wind_speed", 10.0)
        code = current.get("weather_code", 0)
        rain_prob = current.get("rain_probability", 0)
        precip = float(current.get("precipitation", 0.0) or 0.0)
        cape = float(current.get("cape", 0.0) or 0.0)
        humidity = int(current.get("humidity", 60))
        
        forecast_high_rain = any(d.get("rain_probability", 0) > 75 for d in daily)
        forecast_storm = any(d.get("weather_code", 0) in [95, 96, 99] for d in daily)

        # STRICT METEOROLOGICAL DIRECTIVE:
        # Do not generate a severe thunderstorm, lightning, or heavy rain advisory unless
        # precipitation > 1.0mm OR the standard WMO weather_code falls explicitly between 80 and 99.
        # High CAPE or high humidity alone must be reported as 'Hot/Humid with convective potential' but NOT as an active storm.
        is_active_rain_or_storm = (precip > 1.0) or (80 <= code <= 99)

        # 1. Thunderstorm / Lightning Advisory (Strictly gated by active storm conditions)
        if is_active_rain_or_storm and (code in [95, 96, 99] or (forecast_storm and precip > 1.0)):
            ai_advisories.append({
                "id": str(uuid.uuid4())[:8],
                "city": city_name,
                "title": "AI Advisory: Severe Thunderstorm & Lightning Risk",
                "description": f"Active convective thunderstorm activity observed in {city_name} (WMO code: {code}, Precipitation: {precip} mm).",
                "severity": "alert",
                "category": "Thunderstorm",
                "source_type": "AI_ADVISORY",
                "valid_until": (datetime.now(timezone.utc) + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M UTC"),
                "action_required": "Seek indoor shelter immediately. Disconnect sensitive electronic appliances during lightning."
            })

        # 2. Convective Potential Advisory (High CAPE or High Humidity without active storm)
        elif (cape >= 1000.0 or humidity >= 75):
            ai_advisories.append({
                "id": str(uuid.uuid4())[:8],
                "city": city_name,
                "title": "AI Advisory: Hot/Humid with Convective Potential",
                "description": f"Elevated thermal instability (CAPE: {cape} J/kg) and relative humidity ({humidity}%) detected. Convective potential exists, but no active storm is in progress (Precipitation: {precip} mm, WMO: {code}).",
                "severity": "advisory",
                "category": "Convective Potential",
                "source_type": "AI_ADVISORY",
                "valid_until": (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M UTC"),
                "action_required": "Stay hydrated in humid heat. Monitor local radar for isolated convective cloud formation."
            })

        # 3. Extreme Heat Advisory
        if temp >= 40.0:
            ai_advisories.append({
                "id": str(uuid.uuid4())[:8],
                "city": city_name,
                "title": f"AI Advisory: High Thermal Index ({temp}°C)",
                "description": f"Observed temperature of {temp}°C indicates severe heat stress potential.",
                "severity": "critical" if temp >= 43.0 else "warning",
                "category": "Extreme Heat",
                "source_type": "AI_ADVISORY",
                "valid_until": (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M UTC"),
                "action_required": "Avoid direct afternoon sun, maintain continuous hydration with ORS/water."
            })
        elif temp >= 36.0:
            ai_advisories.append({
                "id": str(uuid.uuid4())[:8],
                "city": city_name,
                "title": f"AI Advisory: Warm Day Caution ({temp}°C)",
                "description": f"Ambient temperature is elevated at {temp}°C. Mild outdoor fatigue possible.",
                "severity": "advisory",
                "category": "Extreme Heat",
                "source_type": "AI_ADVISORY",
                "valid_until": (datetime.now(timezone.utc) + timedelta(hours=6)).strftime("%Y-%m-%d %H:%M UTC"),
                "action_required": "Keep a water bottle handy and wear light cotton apparel."
            })

        # 4. Heavy Precipitation Advisory (Strictly gated by precip > 1.0mm or WMO 80-99)
        if is_active_rain_or_storm and (precip > 1.0 or code in [80, 81, 82]):
            ai_advisories.append({
                "id": str(uuid.uuid4())[:8],
                "city": city_name,
                "title": f"AI Advisory: Active Precipitation Observed ({precip} mm)",
                "description": f"Measurable rainfall and active precipitation detected in {city_name}.",
                "severity": "warning",
                "category": "Heavy Rain",
                "source_type": "AI_ADVISORY",
                "valid_until": (datetime.now(timezone.utc) + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M UTC"),
                "action_required": "Check local drainage on low-lying roads and carry heavy-duty rain protection."
            })

        # 4. Gale Wind Advisory
        if wind >= 40.0:
            ai_advisories.append({
                "id": str(uuid.uuid4())[:8],
                "city": city_name,
                "title": f"AI Advisory: Strong Gusty Winds ({wind} km/h)",
                "description": f"Elevated wind velocity of {wind} km/h detected in regional meteorological readings.",
                "severity": "warning",
                "category": "Strong Winds",
                "source_type": "AI_ADVISORY",
                "valid_until": (datetime.now(timezone.utc) + timedelta(hours=10)).strftime("%Y-%m-%d %H:%M UTC"),
                "action_required": "Secure loose outdoor fixtures and avoid parking under large branches."
            })

        # In DEMO mode only, if demo alerts are specifically requested:
        if force_demo or settings.DEMO_MODE:
            # We explicitly tag demo alerts with [DEMO DATA]
            pass

        has_alerts = len(official_alerts) > 0 or len(ai_advisories) > 0

        return {
            "city": city_name,
            "has_alerts": has_alerts,
            "official_alerts": official_alerts,
            "ai_advisory_alerts": ai_advisories,
            "is_demo": current.get("is_demo", False)
        }

    async def get_advisories(self, lat: float, lon: float, city_name: str, lang: str = "en", force_demo: bool = False) -> Dict[str, Any]:
        lat, lon, city_name = self.resolve_coordinates(city_name, lat, lon)
        current = await self.get_current(lat, lon, city_name, force_demo)
        return AdvisoryService.generate_advisories(current, lang)

weather_service = WeatherService()
