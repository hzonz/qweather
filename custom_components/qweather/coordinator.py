"""QWeather (和风天气) 数据协调器 - 带有智能缓存版本."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import homeassistant.util.dt as dt_util

# 导入必要的常量和私钥处理
from cryptography.hazmat.primitives import serialization
import jwt

from .const import (
    DOMAIN, CONF_API_KEY, CONF_LOCATION_ID, CONF_USE_TOKEN,
    CONF_PROJECT_ID, CONF_KEY_ID, CONF_PRIVATE_KEY, CONF_UPDATE_INTERVAL,
    SUGGESTION_TYPE_MAP,
    CONF_DAILYSTEPS, CONF_HOURLYSTEPS, CONF_ALERT, CONF_GIRD, CONF_LIFEINDEX,
)
from .condition import CONDITION_MAP

_LOGGER = logging.getLogger(__name__)

# --- 定义不同数据的缓存有效期 (单位: 秒) ---
TTL_NOW = 0          # 实时天气：跟随主循环同步刷新 (例如 15min)
TTL_DAILY = 3600     # 每日预报：1小时更新一次
TTL_HOURLY = 1800    # 逐小时预报：30分钟更新一次
TTL_INDICES = 10800  # 生活指数：3小时更新一次 (10800s)
TTL_AIR = 1800       # 空气质量：30分钟更新一次
TTL_MINUTELY = 600

class QWeatherUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, version: str) -> None:
        """初始化协调器."""
        self.entry = entry
        self.version = version  # 接收并保存来自 manifest 的版本号
        self.location = entry.data.get(CONF_LOCATION_ID)
        
        # 获取刷新间隔
        update_interval = self.entry.options.get(
            CONF_UPDATE_INTERVAL, 
            self.entry.data.get(CONF_UPDATE_INTERVAL, 15)
        )
        
        super().__init__(
            hass, 
            _LOGGER, 
            name=DOMAIN,
            update_interval=timedelta(minutes=update_interval),
        )
        
        self.session = async_get_clientsession(hass)
        self.city_name: str | None = None
        
        # --- 缓存存储 ---
        self._cache_data: dict[str, Any] = {}
        self._last_update_times: dict[str, float] = {}

    def _should_update(self, category: str, ttl: int) -> bool:
        """检查特定类别的数据是否需要更新."""
        last_time = self._last_update_times.get(category, 0)
        # 如果从没更新过，或者当前时间超过了上次更新时间 + TTL
        return time.time() - last_time > ttl

    async def _async_update_data(self) -> dict[str, Any]:
        """智能获取数据：合并缓存、处理 UI 开关并按需请求 API。"""
        now_ts = time.time()
        tasks = []
        task_map = []

        # --- A. 获取 UI 配置选项 ---
        options = self.entry.options
        # 预报天数/小时数
        daily_steps = options.get(CONF_DAILYSTEPS, 7)
        hourly_steps = options.get(CONF_HOURLYSTEPS, 24)
        # 功能开关
        show_alert = options.get(CONF_ALERT, True)
        show_life = options.get(CONF_LIFEINDEX, True)
        use_grid = options.get(CONF_GIRD, False)  # 格点天气开关

        # 定义 API 前缀 (普通天气 vs 格点天气)
        api_type = "grid-weather" if use_grid else "weather"

        # --- B. 动态构建请求任务 ---

        # 1. 实时天气 (始终请求)
        tasks.append(self._async_fetch_data(f"{api_type}/now"))
        task_map.append("now")

        # 2. 每日预报 (受 TTL 和 天数设置控制)
        if self._should_update("daily", TTL_DAILY):
            # 这里的 endpoint 会变成类似 weather/7d 或 grid-weather/7d
            tasks.append(self._async_fetch_data(f"{api_type}/{daily_steps}d"))
            task_map.append("daily")
        
        # 3. 逐小时预报 (受 TTL 和 小时设置控制)
        if self._should_update("hourly", TTL_HOURLY):
            tasks.append(self._async_fetch_data(f"{api_type}/{hourly_steps}h"))
            task_map.append("hourly")

        # 4. 空气质量 (仅普通 API 支持，TTL 30分钟)
        if self._should_update("air", TTL_AIR):
            tasks.append(self._async_fetch_data("air/now"))
            task_map.append("air")

        # 5. 生活指数 (由 UI 开关控制，TTL 3小时)
        if show_life and self._should_update("indices", TTL_INDICES):
            tasks.append(self._async_fetch_data("indices/1d", {"type": "0"}))
            task_map.append("indices")

        # 6. 气象预警 (由 UI 开关控制，始终尝试获取以保证实时性)
        if show_alert:
            tasks.append(self._async_fetch_data("warning/now"))
            task_map.append("warning")

        # 7. 分钟级降水 (TTL 10分钟)
        if self._should_update("minutely", TTL_MINUTELY):
            tasks.append(self._async_fetch_data("minutely/5m"))
            task_map.append("minutely")

        # 8. 城市名 (仅首次获取)
        if not self.city_name:
            tasks.append(self._async_fetch_city_name_internal())
            task_map.append("city")

        # --- C. 并发请求与异常处理 ---
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as err:
            raise UpdateFailed(f"API 请求失败: {err}")

        # --- D. 解析结果并更新缓存 ---
        new_raw_data = {}
        for i, res in enumerate(results):
            category = task_map[i]
            if isinstance(res, dict) and res:
                new_raw_data[category] = res
                self._last_update_times[category] = now_ts
            elif category == "city" and res:
                self.city_name = res

        # --- E. 数据清洗与摘要合成 ---
        
        # 实时数据
        now_json = new_raw_data.get("now", self._cache_data.get("raw_now", {})).get("now", {})
        self._cache_data["raw_now"] = new_raw_data.get("now", self._cache_data.get("raw_now", {}))
        
        # 逐小时预报及摘要
        hourly_raw = new_raw_data.get("hourly", self._cache_data.get("raw_hourly", {}))
        self._cache_data["raw_hourly"] = hourly_raw
        hourly_list = hourly_raw.get("hourly", [])
        forecast_hourly = self._parse_hourly(hourly_list)
        
        # 合成小时级摘要
        if hourly_list:
            next_6h_text = [h.get("text") for h in hourly_list[:6]]
            unique_text = []
            for t in next_6h_text:
                if t not in unique_text: unique_text.append(t)
            hourly_summary = f"未来6小时：{'转'.join(unique_text)}"
        else:
            hourly_summary = "暂无天气概况"

        # 分钟级降水
        minutely_raw = new_raw_data.get("minutely", self._cache_data.get("raw_minutely", {}))
        self._cache_data["raw_minutely"] = minutely_raw
        minutely_summary = minutely_raw.get("summary", "暂无分钟降水预报")

        # 每日预报
        daily_json = new_raw_data.get("daily", self._cache_data.get("raw_daily", {})).get("daily", [])
        self._cache_data["raw_daily"] = new_raw_data.get("daily", self._cache_data.get("raw_daily", {}))
        forecast_daily = self._parse_daily(daily_json)

        # 生活指数 (如果关闭开关，返回空列表)
        indices_json = []
        if show_life:
            indices_json = new_raw_data.get("indices", self._cache_data.get("raw_indices", {})).get("daily", [])
            self._cache_data["raw_indices"] = new_raw_data.get("indices", self._cache_data.get("raw_indices", {}))
        parsed_indices = self._parse_indices(indices_json)

        # 空气质量
        air_json = new_raw_data.get("air", self._cache_data.get("raw_air", {})).get("now", {})
        self._cache_data["raw_air"] = new_raw_data.get("air", self._cache_data.get("raw_air", {}))
        
        # 预警 (如果关闭开关，返回空列表)
        warning_json = []
        if show_alert:
            warning_json = new_raw_data.get("warning", {}).get("warning", [])

    # --- F. 返回最终结果集 (对齐 V7 官方文档) ---
        return {
            "now": {
                "temp": float(now_json.get("temp")) if now_json.get("temp") else None,
                "text_cn": now_json.get("text"), # 状态文字：如“晴”
                "condition": CONDITION_MAP.get(now_json.get("icon"), "exceptional"),
                "humidity": float(now_json.get("humidity")) if now_json.get("humidity") else None,
                "pressure": float(now_json.get("pressure")) if now_json.get("pressure") else None,
                "windSpeed": float(now_json.get("windSpeed")) if now_json.get("windSpeed") else None,
                "wind360": float(now_json.get("wind360")) if now_json.get("wind360") else None,
                "windDir": now_json.get("windDir"),
                "windScale": now_json.get("windScale"),
                "feelsLike": float(now_json.get("feelsLike")) if now_json.get("feelsLike") else None,
                "icon": now_json.get("icon"),
                "obsTime": now_json.get("obsTime"),
                "vis": float(now_json.get("vis")) if now_json.get("vis") else 0.0,
                "precip": float(now_json.get("precip")) if now_json.get("precip") else 0.0,
                "cloud": float(now_json.get("cloud")) if now_json.get("cloud") else 0.0,
                "dew": float(now_json.get("dew")) if now_json.get("dew") else None,
            },
            "daily": forecast_daily,
            "hourly": forecast_hourly,
            "aqi": air_json,
            "warning": warning_json,
            "indices": parsed_indices,
            "city": self.city_name,
            "minutely_summary": minutely_summary,
            "hourly_summary": hourly_summary,
            "update_time": dt_util.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    # --- 辅助解析方法 (保持代码整洁) ---

    def _parse_daily(self, daily_data: list) -> list:
        forecast = []
        for d in daily_data:
            forecast.append({
                "datetime": f"{d.get('fxDate')}T00:00:00",
                "native_temperature": float(d.get("tempMax", 0)),
                "native_templow": float(d.get("tempMin", 0)),
                "condition": CONDITION_MAP.get(d.get("iconDay"), "exceptional"),
                "icon": d.get("iconDay"),
                "text": d.get("textDay"),
                "native_precipitation": float(d.get("precip", 0)),
                "native_wind_speed": float(d.get("windSpeedDay", 0)),
                "humidity": float(d.get("humidity", 0)),
            })
        return forecast

    def _parse_hourly(self, hourly_data: list) -> list:
        forecast = []
        for h in hourly_data:
            forecast.append({
                "datetime": h.get("fxTime"),
                "native_temperature": float(h.get("temp", 0)),
                "condition": CONDITION_MAP.get(h.get("icon"), "exceptional"),
                "icon": h.get("icon"),
                "text": h.get("text"),
            })
        return forecast

    def _parse_indices(self, indices_data: list) -> list:
        indices = []
        for idx in indices_data:
            indices.append({
                "type": SUGGESTION_TYPE_MAP.get(idx.get("type"), "unknown"),
                "title": idx.get("name"),      # 对应 JS 的 .title
                "title_cn": idx.get("name"),   # 对应 JS 的 .title_cn
                "brf": idx.get("category"),    # 对应 JS 的 .brf
                "txt": idx.get("text"),        # 对应 JS 的 .txt
            })
        return indices

    # --- 基础请求方法 (修复了之前提到的 JWT 和 Host 问题) ---

    async def _async_fetch_data(self, endpoint: str, params: dict | None = None) -> dict:
        url_params = {"location": self.location, "lang": "zh"}
        if params: url_params.update(params)

        headers = {}
        if self.entry.data.get(CONF_USE_TOKEN):
            token = self._generate_jwt()
            if token: headers["Authorization"] = f"Bearer {token}"
        else:
            url_params["key"] = self.entry.data.get(CONF_API_KEY)

        # 修复：动态获取 Host
        host = self.entry.data.get("host", "devapi.qweather.com")
        url = f"https://{host}/v7/{endpoint}"

        try:
            async with asyncio.timeout(10):
                resp = await self.session.get(url, params=url_params, headers=headers)
                data = await resp.json()
                return data if data.get("code") == "200" else {}
        except Exception:
            return {}

    async def _async_fetch_city_name_internal(self) -> str | None:
        """内部调用的城市名获取逻辑 (支持 JWT)。"""
        url = "https://geoapi.qweather.com/v2/city/lookup"
        params = {"location": self.location}
        headers = {}

        # 这里的逻辑应与 _async_fetch_data 保持一致
        if self.entry.data.get(CONF_USE_TOKEN):
            token = self._generate_jwt()
            if token: headers["Authorization"] = f"Bearer {token}"
        else:
            params["key"] = self.entry.data.get(CONF_API_KEY)

        try:
            async with self.session.get(url, params=params, headers=headers) as resp:
                data = await resp.json()
                if data.get("code") == "200":
                    return data["location"][0]["name"]
        except:
            pass
        return "未知地点"

    def _generate_jwt(self) -> str | None:
        # 修复：PEM 字符串转对象
        try:
            key_content = self.entry.data.get(CONF_PRIVATE_KEY)
            if not key_content: return None
            
            private_key_obj = serialization.load_pem_private_key(
                key_content.encode('utf-8'), password=None
            )
            now_ts = int(time.time())
            payload = {'iat': now_ts - 30, 'exp': now_ts + 900, 'sub': self.entry.data.get(CONF_PROJECT_ID)}
            return jwt.encode(payload, private_key_obj, algorithm='EdDSA', headers={'kid': self.entry.data.get(CONF_KEY_ID)})
        except:
            return None
