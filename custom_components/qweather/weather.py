"""QWeather (和风天气) 天气平台实现."""
from __future__ import annotations

import logging
from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.const import (
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, ATTRIBUTION, ATTR_UPDATE_TIME, ATTR_AQI, ATTR_SUGGESTION,CONF_CUSTOM_UI
from .coordinator import QWeatherUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """通过配置条目设置天气实体."""
    # 从 runtime_data 获取在 __init__.py 中初始化的协调器
    coordinator: QWeatherUpdateCoordinator = entry.runtime_data
    
    async_add_entities([
        HeFengWeather(coordinator, entry.unique_id, entry.title)
    ])

class HeFengWeather(CoordinatorEntity[QWeatherUpdateCoordinator], WeatherEntity):
    """和风天气实体类."""

    _attr_has_entity_name = True
    _attr_native_precipitation_unit = UnitOfLength.MILLIMETERS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_visibility_unit = UnitOfLength.KILOMETERS
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR

    def __init__(self, coordinator: QWeatherUpdateCoordinator, unique_id: str, name: str):
        """初始化."""
        super().__init__(coordinator)
        self._attr_unique_id = unique_id
        self._attr_name = None  # 使用设备名称作为实体名称
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_id)},
            name=name,
            manufacturer=MANUFACTURER,
            entry_type=DeviceEntryType.SERVICE,
            sw_version=coordinator.version,
        )
        # 声明支持每日和逐小时预报
        self._attr_supported_features = (
            WeatherEntityFeature.FORECAST_DAILY | 
            WeatherEntityFeature.FORECAST_HOURLY
        )

    @property
    def condition(self) -> str | None:
        """返回当前天气状态."""
        return self.coordinator.data.get("now", {}).get("condition")

    @property
    def native_temperature(self) -> float | None:
        """返回当前温度."""
        return self.coordinator.data.get("now", {}).get("temp")

    @property
    def humidity(self) -> float | None:
        """返回当前湿度."""
        return self.coordinator.data.get("now", {}).get("humidity")

    @property
    def native_pressure(self) -> float | None:
        """返回当前气压."""
        return self.coordinator.data.get("now", {}).get("pressure")

    @property
    def native_wind_speed(self) -> float | None:
        """返回当前风速."""
        return self.coordinator.data.get("now", {}).get("windSpeed")

    @property
    def wind_bearing(self) -> float | str | None:
        """返回风向角度."""
        return self.coordinator.data.get("now", {}).get("wind360")

    @property
    def native_visibility(self) -> float | None:
        """返回能见度."""
        return self.coordinator.data.get("now", {}).get("vis")

    @property
    def native_dew_point(self) -> float | None:
        """返回露点温度."""
        return self.coordinator.data.get("now", {}).get("dew")

    @property
    def cloud_coverage(self) -> float | None:
        """返回云量."""
        return self.coordinator.data.get("now", {}).get("cloud")

    # --- 核心：HA 2024.3+ 预报实现 ---

    async def async_forecast_daily(self) -> list[Forecast] | None:
        """返回每日预报服务数据."""
        return self.coordinator.data.get("daily")

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        """返回逐小时预报服务数据."""
        return self.coordinator.data.get("hourly")

    # --- 扩展属性 (为自定义卡片保留) ---

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data
        if not data: return {}
        now = data.get("now", {})
        
        attrs = {
            "attribution": ATTRIBUTION,
            "city": data.get("city"),
            "qweather_icon": now.get("icon"),
            "update_time": data.get("update_time"),
            "obs_time": now.get("obsTime"),
            "condition_cn": now.get("text_cn"), # 对齐复刻版卡片
        }

        # 重点：将 coordinator 中的字段映射为前端期望的名称
        attrs.update({
            "feels_like": now.get("feelsLike"),
            "wind_dir": now.get("windDir"),
            "wind_scale": now.get("windScale"),
            "humidity": now.get("humidity"),
            "pressure": now.get("pressure"),
            "visibility": now.get("vis"),
            "cloud": now.get("cloud"),
            "precip": now.get("precip"),
            "dew": now.get("dew"),
            "minutely_summary": data.get("minutely_summary"),
            "hourly_summary": data.get("hourly_summary"),
        })

        # 注入复杂对象
        if data.get("aqi"): attrs["aqi"] = data.get("aqi")
        if data.get("warning"): attrs["warning"] = data.get("warning")
        if data.get("indices"): attrs["suggestion"] = data.get("indices")

        if self.coordinator.entry.options.get(CONF_CUSTOM_UI):
            attrs["custom_ui_more_info"] = "qweather-more-info"

        return attrs
