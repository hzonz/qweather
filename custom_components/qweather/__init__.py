"""QWeather (和风天气) 集成入口."""
from __future__ import annotations

import logging
import os
import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform
from homeassistant.helpers.typing import ConfigType
from homeassistant.components.http import StaticPathConfig
from homeassistant.components import frontend

from .const import DOMAIN, PLATFORMS, VERSION

_LOGGER = logging.getLogger(__name__)

# 定义类型别名
type QWeatherConfigEntry = ConfigEntry[QWeatherUpdateCoordinator]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

from .coordinator import QWeatherUpdateCoordinator

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    return True

async def async_setup_entry(hass: HomeAssistant, entry: QWeatherConfigEntry) -> bool:
    """从配置条目设置集成."""
    
    # 1. 动态获取物理路径 (指向到 local 这一层)
    base_path = os.path.dirname(__file__)
    local_path = os.path.join(base_path, "local")
    
    if os.path.exists(local_path):
        # 注册静态路径映射
        await hass.http.async_register_static_paths([
            StaticPathConfig("/qweather-local", local_path, False)
        ])
        
        # 【关键修复】：根据你的目录结构，文件在 local/qweather-card/ 目录下
        # 所以注入 URL 必须包含 qweather-card
        js_url_card = f"/qweather-local/qweather-card/qweather-card.js?v={VERSION}"
        js_url_info = f"/qweather-local/qweather-card/qweather-more-info.js?v={VERSION}"
        
        frontend.add_extra_js_url(hass, js_url_card)
        frontend.add_extra_js_url(hass, js_url_info)
        
        _LOGGER.info("和风天气：已注入 JS 资源 - %s", js_url_card)
    else:
        _LOGGER.error("和风天气：无法找到 local 文件夹，路径应为: %s", local_path)

    # 2. 初始化协调器
    coordinator = QWeatherUpdateCoordinator(hass, entry)
    
    # 3. 执行第一次刷新
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.warning("和风天气：初始数据获取失败 (可能是网络问题): %s", err)

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """当选项更新时重新加载集成."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: QWeatherConfigEntry) -> bool:
    """卸载配置条目."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
