"""
Abstract Weather Provider Interface
Designed for future numerical weather prediction (NWP) model feeds:
GFS, ECMWF, WRF, IMD, etc.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List

class AbstractWeatherProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the weather provider or NWP model"""
        pass

    @abstractmethod
    async def get_current_weather(self, lat: float, lon: float, city_name: str) -> Dict[str, Any]:
        """Fetch real-time weather observations"""
        pass

    @abstractmethod
    async def get_hourly_forecast(self, lat: float, lon: float, city_name: str, hours: int = 24) -> List[Dict[str, Any]]:
        """Fetch hourly forecast up to N hours"""
        pass

    @abstractmethod
    async def get_daily_forecast(self, lat: float, lon: float, city_name: str, days: int = 7) -> List[Dict[str, Any]]:
        """Fetch daily forecast for 7-14 days"""
        pass

    @abstractmethod
    async def get_historical_climate(self, lat: float, lon: float, city_name: str, days_back: int = 30) -> Dict[str, Any]:
        """Fetch historical climate data and trends"""
        pass
