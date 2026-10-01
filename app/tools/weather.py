from datetime import datetime, timezone
from typing import Any, Dict
import httpx


def get_weather(city: str) -> Dict[str, Any]:
    """Live weather via Open-Meteo. No API key required.
    Returns location, current temperature, relevant forecast, source, and timestamp.
    """
    cleaned_city = city.strip().title()
    ts = datetime.now(timezone.utc).isoformat()
    try:
        with httpx.Client(timeout=8.0) as client:
            geo_res = client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": cleaned_city, "count": 1, "language": "en", "format": "json"},
            )
            geo_res.raise_for_status()
            geo = geo_res.json()

            if not geo.get("results"):
                return {
                    "ok": False,
                    "error": f"Could not find coordinates for city: '{cleaned_city}'",
                    "city": cleaned_city,
                    "timestamp": ts,
                    "source": "Open-Meteo Geocoding",
                }

            hit = geo["results"][0]
            lat = hit["latitude"]
            lon = hit["longitude"]

            weather_res = client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
                    "forecast_days": 3,
                    "timezone": "auto",
                },
            )
            weather_res.raise_for_status()
            weather = weather_res.json()

            current = weather.get("current", {})
            daily = weather.get("daily", {})

            # Weather code interpretation
            weather_code = current.get("weather_code", 0)
            condition = "Clear"
            if weather_code in (1, 2, 3):
                condition = "Partly Cloudy / Overcast"
            elif weather_code in (51, 53, 55, 61, 63, 65, 80, 81, 82):
                condition = "Rain / Showers"
            elif weather_code in (95, 96, 99):
                condition = "Thunderstorm"

            rain_chance = None
            if daily.get("precipitation_probability_max"):
                rain_chance = daily["precipitation_probability_max"][0]

            location_name = hit.get("name", cleaned_city)
            admin1 = hit.get("admin1", "")
            country = hit.get("country", "India")
            full_loc = f"{location_name}, {admin1}" if admin1 else location_name

            daily_rain_probs = daily.get("precipitation_probability_max", [])
            tmrw_rain = daily_rain_probs[1] if len(daily_rain_probs) > 1 else rain_chance
            parso_rain = daily_rain_probs[2] if len(daily_rain_probs) > 2 else tmrw_rain

            return {
                "ok": True,
                "source": "Open-Meteo Live API",
                "source_type": "VERIFIED_OFFICIAL",
                "timestamp": ts,
                "city": location_name,
                "full_location": f"{full_loc}, {country}",
                "current_temperature": current.get("temperature_2m"),
                "condition": condition,
                "humidity": current.get("relative_humidity_2m"),
                "rain_probability_today": rain_chance,
                "tomorrow_rain_probability": tmrw_rain,
                "day_after_tomorrow_rain_probability": parso_rain,
                "max_temp": daily.get("temperature_2m_max", [None])[0] if daily.get("temperature_2m_max") else None,
                "min_temp": daily.get("temperature_2m_min", [None])[0] if daily.get("temperature_2m_min") else None,
            }
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Weather service temporarily unavailable: {str(exc)}",
            "city": cleaned_city,
            "timestamp": ts,
            "source": "Open-Meteo Live API",
        }
