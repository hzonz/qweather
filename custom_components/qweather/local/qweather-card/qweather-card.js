/**
 * QWeather Dashboard Card - Professional Full Version
 */

(async () => {
  const whenDefined = (tag) => customElements.whenDefined(tag);
  await Promise.race([whenDefined("ha-card"), whenDefined("ha-panel-lovelace")]);

  const LitElement = window.LitElement || Object.getPrototypeOf(customElements.get("ha-card"));
  const html = LitElement.prototype.html;
  const css = LitElement.prototype.css;

  class QWeatherCard extends LitElement {
    static get properties() {
      return {
        hass: { type: Object },
        config: { type: Object },
        _forecastDaily: { type: Array, state: true },
        _forecastHourly: { type: Array, state: true },
        _weather: { state: true },
        _selectedTab: { type: String, state: true }
      };
    }

    static getStubConfig() { return { entity: "weather.qweather_pro_weather" }; }

    constructor() {
      super();
      this._forecastDaily = [];
      this._forecastHourly = [];
      this._selectedTab = 'daily';
      this._unsubs = [];
    }

    setConfig(config) {
      this.config = { entity: "weather.qweather_pro_weather", ...config };
    }

    set hass(hass) {
      this._hass = hass;
      const entityId = this.config.entity;
      const state = hass.states[entityId];

      if (state && this._weather !== state) {
        const oldId = this._weather?.entity_id;
        this._weather = state;
        if (oldId !== entityId) this._subscribeForecasts();
      }
    }

    async _subscribeForecasts() {
      this._clearSubs();
      const entityId = this.config.entity;
      try {
        const subD = await this._hass.connection.subscribeMessage(
          (msg) => { this._forecastDaily = msg.forecast; this.requestUpdate(); },
          { type: "weather/subscribe_forecast", entity_id: entityId, forecast_type: "daily" }
        );
        this._unsubs.push(subD);

        const subH = await this._hass.connection.subscribeMessage(
          (msg) => { this._forecastHourly = msg.forecast; this.requestUpdate(); },
          { type: "weather/subscribe_forecast", entity_id: entityId, forecast_type: "hourly" }
        );
        this._unsubs.push(subH);
      } catch (e) { console.error("订阅失败", e); }
    }

    _clearSubs() { while (this._unsubs.length) { const unsub = this._unsubs.pop(); if (unsub) unsub(); } }
    disconnectedCallback() { this._clearSubs(); super.disconnectedCallback(); }

    _handleTabClick(e, tab) {
      e.stopPropagation();
      this._selectedTab = tab;
    }

    _getIcon(code) { return `/qweather-local/qweather-card/icons/${code || '100'}.svg`; }

    _formatDate(datetime) {
      const d = new Date(datetime);
      if (d.getDate() === new Date().getDate()) return "今天";
      const days = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
      return days[d.getDay()];
    }

    _formatTime(datetime) {
      const d = new Date(datetime);
      let hours = d.getHours();
      return (hours < 10 ? '0' + hours : hours) + ':00';
    }

    render() {
      if (!this._weather) return html`<ha-card class="loading">加载中...</ha-card>`;
      
      const attr = this._weather.attributes;
      const isDaily = this._selectedTab === 'daily';
      const forecast = isDaily ? this._forecastDaily : this._forecastHourly;
      
      const aqiVal = attr.aqi?.aqi || attr.aqi || '--';
      const aqiCat = attr.aqi?.category || '';

      return html`
        <ha-card @click="${this._handleMoreInfo}">
          <!-- 1. 页眉 -->
          <div class="header">
            <div class="header-left">
              <div class="weather-icon-circle">
                <img src="${this._getIcon(attr.qweather_icon)}">
              </div>
              <div>
                <div class="condition-state">${attr.condition_cn || this._weather.state}</div>
                <div class="city-name">${this.config.name || attr.city || '和风天气'}</div>
              </div>
            </div>
            <div class="header-right">
              <div class="current-temp">${Math.round(attr.temperature)}<span>°C</span></div>
              <div class="update-time">${attr.update_time?.split(' ')[1] || ''} 更新</div>
            </div>
          </div>

          <!-- 2. 预警 -->
          ${attr.warning?.length > 0 ? attr.warning.map(w => html`
            <div class="warning-section">
              <ha-icon icon="mdi:alert-circle"></ha-icon>
              <div>
                <div style="font-weight: bold;">${w.title}</div>
                <div style="font-size: 12px; margin-top: 2px;">${w.text}</div>
              </div>
            </div>
          `) : ''}

          <!-- 3. 简报 -->
          <div class="briefing-box">
            <div class="brief-item">
              <ha-icon icon="mdi:bullseye-arrow"></ha-icon>
              <div class="brief-content">
                <span class="brief-label">分钟降水：</span>
                <span class="brief-value">${attr.minutely_summary || '未来两小时无降水'}</span>
              </div>
            </div>
            <div class="brief-item">
              <ha-icon icon="mdi:weather-partly-cloudy"></ha-icon>
              <div class="brief-content">
                <span class="brief-label">天气概况：</span>
                <span class="brief-value">${attr.hourly_summary || '近期天气平稳'}</span>
              </div>
            </div>
          </div>

          <!-- 4. 2x2 网格 -->
          <div class="attributes-grid">
            ${this._renderAttr('mdi:water-percent', '湿度', `${attr.humidity}%`)}
            ${this._renderAttr('mdi:gauge', '气压', `${attr.pressure}hPa`)}
            ${this._renderAttr('mdi:weather-windy', '风速', `${attr.windscale || attr.wind_speed}级`)}
            ${this._renderAttr('mdi:air-filter', '空气质量', `${aqiVal} ${aqiCat}`.trim())}
          </div>

          <!-- 5. 选项卡 -->
          <div class="tabs">
            <div class="tab ${isDaily ? 'active' : ''}" @click=${(e) => this._handleTabClick(e, 'daily')}>每日预报</div>
            <div class="tab ${!isDaily ? 'active' : ''}" @click=${(e) => this._handleTabClick(e, 'hourly')}>小时预报</div>
          </div>

          <!-- 6. 滚动预报列表 -->
          <div class="forecast-scroll-container">
            ${(!forecast || forecast.length === 0) 
              ? html`<div class="data-loading">正在订阅数据...</div>` 
              : forecast.slice(0, isDaily ? 7 : 24).map(item => html`
                <div class="f-row">
                  <div class="f-date">
                    ${isDaily ? this._formatDate(item.datetime) : this._formatTime(item.datetime)}
                  </div>
                  <div class="f-icon-box">
                    <img class="f-icon" src="${this._getIcon(item.icon)}">
                    ${isDaily ? html`<span class="f-condition-text">${item.text || ''}</span>` : ''}
                  </div>
                  <div class="f-temp">
                    ${Math.round(item.temperature)}°
                    ${isDaily ? html`<span class="f-low">${Math.round(item.templow)}°</span>` : ''}
                  </div>
                </div>
            `)}
          </div>
          
          <div class="attribution">${attr.attribution}</div>
        </ha-card>
      `;
    }

    _renderAttr(icon, label, value) {
      return html`
        <div class="attr-item">
          <ha-icon .icon=${icon}></ha-icon>
          <div><div class="attr-label">${label}</div><div class="attr-value">${value}</div></div>
        </div>
      `;
    }

    _handleMoreInfo() {
      const event = new CustomEvent("hass-more-info", {
        detail: { entityId: this.config.entity },
        bubbles: true, composed: true,
      });
      this.dispatchEvent(event);
    }

    static get styles() {
      return css`
        :host { display: block; --primary-color: #03a9f4; }
        ha-card { padding: 18px; cursor: pointer; border-radius: 12px; }
        
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
        .header-left { display: flex; align-items: center; }
        .weather-icon-circle {
          width: 56px; height: 56px; margin-right: 16px; border-radius: 50%;
          background-color: var(--secondary-background-color);
          display: flex; align-items: center; justify-content: center;
        }
        .weather-icon-circle img { width: 36px; height: 36px; }
        .condition-state { font-size: 22px; font-weight: 500; }
        .city-name { font-size: 13px; color: var(--secondary-text-color); }
        .current-temp { font-size: 34px; font-weight: 300; line-height: 1; }
        .current-temp span { font-size: 16px; vertical-align: top; margin-left: 2px; }
        .update-time { font-size: 11px; color: var(--secondary-text-color); margin-top: 4px; }

        .warning-section { background-color: var(--error-color); color: white; padding: 12px; border-radius: 8px; margin-bottom: 20px; display: flex; align-items: flex-start; gap: 12px; }
        .warning-section ha-icon { color: white; --mdc-icon-size: 22px; }

        .briefing-box { background: var(--secondary-background-color); padding: 12px; border-radius: 10px; margin-bottom: 24px; display: flex; flex-direction: column; gap: 8px; }
        .brief-item { display: flex; align-items: center; gap: 10px; }
        .brief-item ha-icon { color: var(--primary-color); --mdc-icon-size: 18px; }
        .brief-label { font-size: 12px; color: var(--secondary-text-color); font-weight: bold; }
        .brief-value { font-size: 13px; color: var(--primary-text-color); }

        .attributes-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }
        .attr-item { display: flex; align-items: center; }
        .attr-item ha-icon { margin-right: 14px; color: var(--secondary-text-color); --mdc-icon-size: 20px; }
        .attr-label { font-size: 11px; color: var(--secondary-text-color); }
        .attr-value { font-size: 14px; font-weight: 500; }

        .tabs { display: flex; border-bottom: 1px solid var(--divider-color); margin-bottom: 16px; }
        .tab { padding: 10px 20px; cursor: pointer; font-size: 13px; font-weight: 500; color: var(--secondary-text-color); border-bottom: 2px solid transparent; }
        .tab.active { color: var(--primary-color); border-bottom-color: var(--primary-color); }

        /* --- 滚动容器核心样式 --- */
        .forecast-scroll-container {
          max-height: 280px; /* 限制最高显示约 6-7 行 */
          overflow-y: auto;
          overflow-x: hidden;
          padding-right: 4px;
        }
        
        /* 美化滚动条 */
        .forecast-scroll-container::-webkit-scrollbar { width: 4px; }
        .forecast-scroll-container::-webkit-scrollbar-track { background: transparent; }
        .forecast-scroll-container::-webkit-scrollbar-thumb { 
          background: var(--divider-color); 
          border-radius: 4px; 
        }

        .f-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid var(--divider-color); }
        .f-row:last-child { border-bottom: none; }
        .f-date { width: 80px; font-size: 13px; }
        .f-icon-box { flex: 1; display: flex; align-items: center; justify-content: center; gap: 8px; }
        .f-icon { width: 24px; height: 24px; }
        .f-condition-text { font-size: 12px; color: var(--secondary-text-color); }
        .f-temp { width: 90px; text-align: right; font-size: 13px; font-weight: 500; }
        .f-low { color: var(--secondary-text-color); margin-left: 4px; }

        .data-loading { padding: 30px; text-align: center; font-size: 13px; color: var(--secondary-text-color); font-style: italic; }
        .attribution { text-align: center; font-size: 9px; color: var(--secondary-text-color); margin-top: 16px; opacity: 0.6; }
        .loading { padding: 40px; text-align: center; }
      `;
    }
  }

  customElements.define("qweather-card", QWeatherCard);
  
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "qweather-card",
    name: "和风天气Pro",
    preview: true,
    description: "具备专业气象预警与简报的高性能Pro级卡片"
  });
})();
