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
from homeassistant.loader import async_get_integration  # 引入动态加载工具

from .const import DOMAIN, PLATFORMS
from .coordinator import QWeatherUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# 定义类型别名
type QWeatherConfigEntry = ConfigEntry[QWeatherUpdateCoordinator]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """初始化集成（不支持 YAML）。"""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: QWeatherConfigEntry) -> bool:
    """从配置条目设置集成."""
    
    # 1. 动态获取 manifest.json 信息 (包括版本号)
    integration = await async_get_integration(hass, DOMAIN)
    version = integration.version
    
    # 2. 动态获取物理路径并注册静态资源
    base_path = os.path.dirname(__file__)
    local_path = os.path.join(base_path, "local")
    
    if os.path.exists(local_path):
        # 注册静态路径映射
        await hass.http.async_register_static_paths([
            StaticPathConfig("/qweather-local", local_path, False)
        ])
        
        # 使用从 manifest 获取的 version 注入 URL，防止前端缓存旧版 JS
        js_url_card = f"/qweather-local/qweather-card/qweather-card.js?v={version}"
        js_url_info = f"/qweather-local/qweather-card/qweather-more-info.js?v={version}"
        
        frontend.add_extra_js_url(hass, js_url_card)
        frontend.add_extra_js_url(hass, js_url_info)
        
        _LOGGER.info("和风天气 (版本 %s)：已注入 Lovelace JS 资源", version)
    else:
        _LOGGER.error("和风天气：无法找到 local 文件夹，路径应为: %s", local_path)

    # 3. 初始化协调器 (将 version 传入)
    # 注意：请确保你的 coordinator.py 中的 __init__ 接收 version 参数
    coordinator = QWeatherUpdateCoordinator(hass, entry, version)
    
    # 4. 执行第一次刷新
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.warning("和风天气：初始数据获取失败 (请检查网络或 API Key): %s", err)

    # 5. 存储协调器数据并加载平台
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # 6. 注册选项更新监听器
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """当选项更新时重新加载集成."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: QWeatherConfigEntry) -> bool:
    """卸载配置条目."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
