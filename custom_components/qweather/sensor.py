"""QWeather (和风天气) 传感器平台."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, ATTRIBUTION
from .coordinator import QWeatherUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True, kw_only=True)
class QWeatherSensorEntityDescription(SensorEntityDescription):
    """自定义描述类，确保 key 用于唯一标识，translation_key 用于命名."""
    value_fn: Callable[[dict[str, Any]], Any]
    attr_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None

# 核心传感器定义
SENSOR_DESCRIPTIONS: tuple[QWeatherSensorEntityDescription, ...] = (
    # 1. 空气质量
    QWeatherSensorEntityDescription(
        key="aqi",
        translation_key="aqi",
        icon="mdi:air-filter",
        # 修正键名为 aqi (对应 coordinator 返回的键)
        value_fn=lambda data: data.get("aqi", {}).get("category", "未知"),
        # 新增 attr_fn，将 PM2.5, PM10 等数据放入属性
        attr_fn=lambda data: {
            "pm2p5": data.get("aqi", {}).get("pm2p5"),
            "pm10": data.get("aqi", {}).get("pm10"),
            "no2": data.get("aqi", {}).get("no2"),
            "so2": data.get("aqi", {}).get("so2"),
            "o3": data.get("aqi", {}).get("o3"),
            "co": data.get("aqi", {}).get("co"),
            "primary": data.get("aqi", {}).get("primary"),
        },
    ),
    # 2. 今日温度范围
    QWeatherSensorEntityDescription(
        key="today_temp_range",
        translation_key="today_temp_range",
        icon="mdi:thermometer-lines",
        value_fn=lambda data: (
            # 注意：这里读取的是 Coordinator 清洗后的 native_... 字段
            f"{int(daily[0].get('native_templow'))}°C/{int(daily[0].get('native_temperature'))}°C"
            if (daily := data.get("daily")) and len(daily) > 0 else "未知"
        ),
        attr_fn=lambda data: {
            "max_temp": daily[0].get("native_temperature") if (daily := data.get("daily")) else None,
            "min_temp": daily[0].get("native_templow") if (daily := data.get("daily")) else None,
        },
    ),
    # 3. 气象预警
    QWeatherSensorEntityDescription(
        key="warning_count",
        translation_key="warning_count",
        icon="mdi:alert-decagram",
        value_fn=lambda data: len(data.get("warning", [])),
    ),
    # 新增：分钟级降水简报传感器
    QWeatherSensorEntityDescription(
        key="precipitation_summary",
        translation_key="precipitation_summary",
        icon="mdi:message-text-clock",
        # 直接读取协调器中的简报
        value_fn=lambda data: data.get("minutely_summary"),
    ),
    
    # 新增：天气概况简报传感器
    QWeatherSensorEntityDescription(
        key="weather_summary",
        translation_key="weather_summary",
        icon="mdi:weather-partly-cloudy",
        value_fn=lambda data: data.get("hourly_summary"),
    ),
)

async def async_setup_entry(hass, entry, async_add_entities):
    """设置平台实体."""
    # 在 2026 版 HA 中，集成数据通常存储在 entry.runtime_data
    coordinator: QWeatherUpdateCoordinator = entry.runtime_data
    unique_id = entry.unique_id or entry.entry_id
    
    async_add_entities(
        QWeatherSensor(coordinator, unique_id, description)
        for description in SENSOR_DESCRIPTIONS
    )

class QWeatherSensor(CoordinatorEntity[QWeatherUpdateCoordinator], SensorEntity):
    """强制显式命名的传感器."""

    # 1. 依然保留这个，用于在 UI 显示时美化名称
    _attr_has_entity_name = True

    def __init__(self, coordinator, unique_id, description):
        super().__init__(coordinator)
        self.entity_description = description
        
        # --- 核心修改：强制指定 Entity ID 的后缀 ---
        # 假设 DOMAIN 是 "qweather"
        # 这样生成的 ID 就会是 sensor.qweather_aqi, sensor.qweather_today_temp_range 等
        # 如果你希望前缀是 he_feng_tian_qi，可以将 DOMAIN 换成该字符串
        self.entity_id = f"sensor.{DOMAIN}_{description.key}"

        # 2. 内部唯一 ID，保持不变，防止配置冲突
        self._attr_unique_id = f"{unique_id}_{description.key}"
        
        # 3. 翻译键，用于 UI 显示名称（如“空气质量”）
        self._attr_translation_key = description.translation_key
        
        # 4. 设备信息
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_id)},
            name=coordinator.entry.title, 
            manufacturer=MANUFACTURER,
            entry_type=DeviceEntryType.SERVICE,
            sw_version=coordinator.version,
        )

    @property
    def native_value(self) -> Any:
        """从 Coordinator 获取数据."""
        if not self.coordinator.data:
            return None
        # 调用描述符中定义的 value_fn
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """添加额外属性."""
        attrs = {"attribution": ATTRIBUTION}
        if self.entity_description.attr_fn:
            try:
                custom_attrs = self.entity_description.attr_fn(self.coordinator.data)
                if custom_attrs:
                    attrs.update(custom_attrs)
            except (KeyError, IndexError, TypeError):
                pass
        return attrs
