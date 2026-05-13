"""QWeather (和风天气) 配置流实现."""
from __future__ import annotations

import logging
import asyncio
import time
import re
from typing import Any

import voluptuous as vol
import jwt
from cryptography.hazmat.primitives import serialization

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_HOST, CONF_API_KEY, CONF_NAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_USE_TOKEN,
    CONF_LOCATION_ID,
    CONF_HOURLYSTEPS,
    CONF_DAILYSTEPS,
    CONF_LIFEINDEX,
    CONF_UPDATE_INTERVAL,
    CONF_PROJECT_ID,
    CONF_KEY_ID,
    CONF_PRIVATE_KEY,
    CONF_ALERT,
    CONF_GIRD,
    CONF_CUSTOM_UI,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_HOST = "api.qweather.com"
DEFAULT_NAME = "和风天气"

class QWeatherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """处理和风天气的配置流."""

    VERSION = 1

    def __init__(self) -> None:
        """初始化."""
        self._temp_data: dict[str, Any] = {}
        self._generated_private_key: str | None = None
        self._generated_public_key: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> QWeatherOptionsFlow:
        """获取选项流."""
        return QWeatherOptionsFlow()

    def _generate_key_pair_sync(self) -> tuple[str, str]:
        """同步生成密钥对."""
        from cryptography.hazmat.primitives.asymmetric import ed25519
        private_key = ed25519.Ed25519PrivateKey.generate()
        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        public_bytes = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return private_bytes.decode('utf-8'), public_bytes.decode('utf-8')

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """初始配置步骤."""
        if user_input is not None:
            self._temp_data = user_input
            if user_input.get(CONF_USE_TOKEN):
                return await self.async_step_jwt_setup()
            return await self._async_verify_and_create(user_input)

        default_location = f"{round(self.hass.config.longitude, 2)},{round(self.hass.config.latitude, 2)}"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_LOCATION_ID, default=default_location): str,
                vol.Required(CONF_USE_TOKEN, default=False): bool,
                vol.Optional(CONF_API_KEY): str,
            })
        )

    async def async_step_jwt_setup(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """处理 JWT 认证步骤."""
        errors: dict[str, str] = {}
        if not self._generated_private_key:
            self._generated_private_key, self._generated_public_key = await self.hass.async_add_executor_job(
                self._generate_key_pair_sync
            )

        if user_input is not None:
            config_data = {
                **self._temp_data, 
                **user_input, 
                CONF_PRIVATE_KEY: self._generated_private_key
            }
            return await self._async_verify_and_create(config_data)

        return self.async_show_form(
            step_id="jwt_setup",
            data_schema=vol.Schema({
                vol.Required(CONF_PROJECT_ID): str,
                vol.Required(CONF_KEY_ID): str,
            }),
            description_placeholders={"public_key": self._generated_public_key}
        )

    async def _async_verify_and_create(self, config_data: dict[str, Any]) -> FlowResult:
        """核心验证与创建逻辑."""
        errors: dict[str, str] = {}
        session = async_get_clientsession(self.hass)
        raw_location = config_data[CONF_LOCATION_ID]
        normalized_location = raw_location.replace(" ", "")
        config_data[CONF_LOCATION_ID] = normalized_location 
        
        headers = {}

        # ... (中间的 JWT 签名逻辑和 API 验证逻辑保持不变) ...

        # 在函数最后生成 unique_id 的地方
        # 使用标准化后的坐标生成唯一 ID
        unique_id = f"qw_{normalized_location.replace(',', '_')}"
        
        # 这一步非常关键：它会告诉 HA 如果 ID 已存在，就弹回错误提示
        await self.async_set_unique_id(unique_id)
        
        # 如果是重新配置模式，我们不需要检查冲突，直接更新即可
        if self.source != config_entries.SOURCE_RECONFIGURE:
            self._abort_if_unique_id_configured()

        return self.async_create_entry(title=config_data[CONF_NAME], data=config_data)

        # 1. JWT 签名逻辑加固
        if config_data.get(CONF_USE_TOKEN):
            try:
                # 必须将 PEM 字符串加载为 Key 对象
                private_key_obj = serialization.load_pem_private_key(
                    config_data[CONF_PRIVATE_KEY].encode('utf-8'),
                    password=None
                )
                now_ts = int(time.time())
                payload = {'iat': now_ts - 30, 'exp': now_ts + 3600, 'sub': config_data[CONF_PROJECT_ID]}
                token = jwt.encode(
                    payload, 
                    private_key_obj, 
                    algorithm='EdDSA', 
                    headers={'kid': config_data[CONF_KEY_ID]}
                )
                headers["Authorization"] = f"Bearer {token}"
            except Exception as err:
                _LOGGER.error("JWT Error: %s", err)
                errors["base"] = "jwt_error"
        else:
            if not config_data.get(CONF_API_KEY):
                errors["base"] = "api_key_missing"
            else:
                headers["X-QW-Api-Key"] = config_data[CONF_API_KEY]

        if not errors:
            # 2. 验证 API (以地理查询为例)
            try:
                geo_url = "https://geoapi.qweather.com/v2/city/lookup"
                params = {"location": config_data[CONF_LOCATION_ID]}
                if not config_data.get(CONF_USE_TOKEN):
                    params["key"] = config_data[CONF_API_KEY]

                async with asyncio.timeout(10):
                    resp = await session.get(geo_url, params=params, headers=headers)
                    res = await resp.json()
                    if res.get("code") != "200":
                        errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"

        # 如果有错，返回对应的表单
        if errors:
            if config_data.get(CONF_USE_TOKEN):
                return self.async_show_form(
                    step_id="jwt_setup",
                    data_schema=vol.Schema({
                        vol.Required(CONF_PROJECT_ID, default=config_data.get(CONF_PROJECT_ID)): str,
                        vol.Required(CONF_KEY_ID, default=config_data.get(CONF_KEY_ID)): str,
                    }),
                    description_placeholders={"public_key": self._generated_public_key},
                    errors=errors
                )
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({
                    vol.Required(CONF_HOST, default=config_data.get(CONF_HOST)): str,
                    vol.Required(CONF_NAME, default=config_data.get(CONF_NAME)): str,
                    vol.Required(CONF_LOCATION_ID, default=config_data.get(CONF_LOCATION_ID)): str,
                    vol.Required(CONF_USE_TOKEN, default=False): bool,
                    vol.Optional(CONF_API_KEY, default=config_data.get(CONF_API_KEY)): str,
                }),
                errors=errors
            )

        # ========================== 修复 NoneType 错误的核心位置 ==========================
        # 3. 成功逻辑：区分重新配置和新创建
        if self.source == config_entries.SOURCE_RECONFIGURE:
            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(), data=config_data
            )

        # 设置唯一 ID 防止重复添加
        unique_id = f"qw_{config_data[CONF_LOCATION_ID].replace(',', '_')}"
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        # 【关键：这里必须有一个 return！】
        return self.async_create_entry(title=config_data[CONF_NAME], data=config_data)
        # ==============================================================================

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """处理重新配置."""
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            return await self._async_verify_and_create({**entry.data, **user_input})

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({
                vol.Required(CONF_API_KEY, default=entry.data.get(CONF_API_KEY, "")): str,
            })
        )

class QWeatherOptionsFlow(config_entries.OptionsFlow):
    """处理和风天气集成的选项配置（集成界面点击“选项”时弹出）。"""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """管理选项步骤。"""
        if user_input is not None:
            # 使用最新的 API 更新配置并自动触发集成的重新加载
            return self.async_create_entry(title="", data=user_input)

        # 获取当前的配置和选项，以便设置 UI 的默认值
        options = self.config_entry.options
        data = self.config_entry.data

        # 构造配置架构
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                # 1. 刷新间隔 (5 - 1440 分钟)
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=options.get(CONF_UPDATE_INTERVAL, data.get(CONF_UPDATE_INTERVAL, 15)),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=1440)),

                # 2. 每日预报天数 (3 - 15 天)
                vol.Optional(
                    CONF_DAILYSTEPS,
                    default=options.get(CONF_DAILYSTEPS, data.get(CONF_DAILYSTEPS, 7)),
                ): vol.All(vol.Coerce(int), vol.Range(min=3, max=15)),

                # 3. 逐小时预报时长 (24 - 168 小时)
                vol.Optional(
                    CONF_HOURLYSTEPS,
                    default=options.get(CONF_HOURLYSTEPS, data.get(CONF_HOURLYSTEPS, 24)),
                ): vol.All(vol.Coerce(int), vol.Range(min=24, max=168)),

                # 4. 开启气象预警
                vol.Optional(
                    CONF_ALERT,
                    default=options.get(CONF_ALERT, data.get(CONF_ALERT, True)),
                ): bool,

                # 5. 开启生活指数
                vol.Optional(
                    CONF_LIFEINDEX,
                    default=options.get(CONF_LIFEINDEX, data.get(CONF_LIFEINDEX, True)),
                ): bool,

                # 6. 开启格点天气 (Grid)
                vol.Optional(
                    CONF_GIRD,
                    default=options.get(CONF_GIRD, data.get(CONF_GIRD, False)),
                ): bool,

                # 7. 自定义 UI 模式
                vol.Optional(
                    CONF_CUSTOM_UI,
                    default=options.get(CONF_CUSTOM_UI, data.get(CONF_CUSTOM_UI, False)),
                ): bool,
            }),
        )
