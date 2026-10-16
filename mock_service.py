from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from app.services.weather_base import AbstractWeatherProvider
from app.core.constants import DEFAULT_CITIES

class MockWeatherProvider(AbstractWeatherProvider):
    @property
    def provider_name(self) -> str:
        return "WeatherGPT Demo Provider (Simulated Indian Met Archive)"

    async def get_current_weather(self, lat: float, lon: float, city_name: str) -> Dict[str, Any]:
        # Realistic city-specific variations for demo simulation
        city_lower = (city_name or "").lower()
        if "delhi" in city_lower:
            base_t, fl, hum, cond, icon, code = 31.2, 34.0, 58, "Mainly Clear", "SunDim", 1
        elif "bengaluru" in city_lower or "bangalore" in city_lower:
            base_t, fl, hum, cond, icon, code = 23.5, 24.2, 68, "Partly Cloudy", "CloudSun", 2
        elif "chennai" in city_lower:
            base_t, fl, hum, cond, icon, code = 29.8, 34.5, 82, "Partly Cloudy", "CloudSun", 2
        elif "hyderabad" in city_lower:
            base_t, fl, hum, cond, icon, code = 27.4, 29.8, 64, "Clear Sky", "Sun", 0
        elif "mumbai" in city_lower:
            base_t, fl, hum, cond, icon, code = 26.8, 30.4, 84, "Moderate Rain", "CloudRain", 62
        else:
            base_t, fl, hum, cond, icon, code = 28.1, 33.2, 78, "Partly Cloudy", "CloudSun", 2

        return {
            "city": city_name,
            "latitude": lat,
            "longitude": lon,
            "temperature": base_t,
            "feels_like": fl,
            "condition": cond,
            "weather_code": code,
            "icon": icon,
            "humidity": hum,
            "precipitation": 2.5 if code > 60 else 0.0,
            "cape": 450.0,
            "wind_speed": 12.5,
            "wind_direction": 140.0,
            "wind_compass": "SE",
            "pressure": 1011.8,
            "visibility": 9.0,
            "rain_probability": 30 if code > 50 else 15,
            "sunrise": "05:54",
            "sunset": "18:22",
            "uv_index": 6.5,
            "uv_risk": "High",
            "air_quality_aqi": 75,
            "air_quality_desc": "Moderate",
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "source": self.provider_name,
            "is_demo": True
        }

    async def get_hourly_forecast(self, lat: float, lon: float, city_name: str, hours: int = 24) -> List[Dict[str, Any]]:
        base_temp = 28.0
        out = []
        now = datetime.now()
        for i in range(hours):
            h_time = now + timedelta(hours=i)
            # simulate diurnal temperature curve
            hour_of_day = h_time.hour
            temp_offset = 4.0 if 11 <= hour_of_day <= 15 else (-3.0 if 2 <= hour_of_day <= 6 else 0.0)
            rain_prob = 40 if 14 <= hour_of_day <= 18 else 15
            
            out.append({
                "time": h_time.strftime("%Y-%m-%dT%H:00"),
                "hour_label": h_time.strftime("%H:00"),
                "temperature": round(base_temp + temp_offset + (i % 2) * 0.4, 1),
                "rain_probability": rain_prob,
                "weather_code": 2 if rain_prob < 30 else 61,
                "condition": "Partly Cloudy" if rain_prob < 30 else "Slight Rain",
                "icon": "CloudSun" if rain_prob < 30 else "CloudRain",
                "wind_speed": round(12.0 + (i % 5) * 1.2, 1),
                "humidity": 68 + (i % 10)
            })
        return out

    async def get_daily_forecast(self, lat: float, lon: float, city_name: str, days: int = 7) -> List[Dict[str, Any]]:
        now = datetime.now()
        day_names = ["Today", "Tomorrow", "Wed", "Thu", "Fri", "Sat", "Sun"]
        conditions = [
            ("Partly Cloudy", "CloudSun", 2, 32.0, 24.5, 20, 14.0),
            ("Scattered Showers", "CloudRain", 61, 30.5, 24.0, 55, 18.2),
            ("Thunderstorm", "CloudLightning", 95, 28.0, 23.0, 80, 24.5),
            ("Mainly Clear", "SunDim", 1, 33.2, 25.0, 10, 11.0),
            ("Sunny & Hot", "Sun", 0, 35.0, 26.0, 5, 9.5),
            ("Partly Cloudy", "CloudSun", 2, 32.5, 25.2, 15, 12.0),
            ("Overcast", "Cloud", 3, 31.0, 24.8, 30, 13.5),
        ]
        out = []
        for i in range(days):
            d_time = now + timedelta(days=i)
            cond_data = conditions[i % len(conditions)]
            out.append({
                "date": d_time.strftime("%Y-%m-%d"),
                "day_name": "Today" if i == 0 else ("Tomorrow" if i == 1 else d_time.strftime("%a")),
                "weather_code": cond_data[2],
                "condition": cond_data[0],
                "icon": cond_data[1],
                "temp_max": cond_data[3],
                "temp_min": cond_data[4],
                "rain_probability": cond_data[5],
                "wind_speed_max": cond_data[6],
                "uv_index_max": 7.2 if i % 2 == 0 else 5.5,
                "sunrise": "05:52",
                "sunset": "18:24"
            })
        return out

    async def get_historical_climate(self, lat: float, lon: float, city_name: str, days_back: int = 30) -> Dict[str, Any]:
        now = datetime.now()
        records = []
        for i in range(days_back, 0, -1):
            past_date = now - timedelta(days=i)
            records.append({
                "date": past_date.strftime("%Y-%m-%d"),
                "temp_max": round(31.5 + (i % 5) * 0.4, 1),
                "temp_min": round(23.5 + (i % 3) * 0.3, 1),
                "temp_mean": round(27.5 + (i % 4) * 0.2, 1),
                "precipitation": round(4.5 if i % 6 == 0 else 0.0, 1)
            })
        return {
            "city": city_name,
            "time_span": f"Past {days_back} Days (Demo Archive)",
            "avg_temperature": 27.8,
            "total_rainfall_mm": 54.2,
            "anomaly_summary": "Simulated meteorological baseline indicates normal seasonal monsoon patterns with stable humidity and thermal index.",
            "historical_records": records,
            "monthly_averages": [
                {"month": "Jan", "avg_temp": 24.5, "rainfall_mm": 12.0},
                {"month": "Feb", "avg_temp": 26.2, "rainfall_mm": 18.0},
                {"month": "Mar", "avg_temp": 28.8, "rainfall_mm": 24.0},
                {"month": "Apr", "avg_temp": 31.0, "rainfall_mm": 35.0},
                {"month": "May", "avg_temp": 33.5, "rainfall_mm": 65.0},
                {"month": "Jun", "avg_temp": 31.2, "rainfall_mm": 140.0},
                {"month": "Jul", "avg_temp": 29.5, "rainfall_mm": 185.0},
                {"month": "Aug", "avg_temp": 29.2, "rainfall_mm": 190.0},
                {"month": "Sep", "avg_temp": 29.0, "rainfall_mm": 165.0},
                {"month": "Oct", "avg_temp": 28.4, "rainfall_mm": 150.0},
                {"month": "Nov", "avg_temp": 26.5, "rainfall_mm": 80.0},
                {"month": "Dec", "avg_temp": 24.8, "rainfall_mm": 15.0}
            ],
            "is_demo": True
        }
