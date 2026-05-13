/**
 * QWeather More Info - Suggestion Focused Version (2026 Optimized)
 */

(async () => {
  const whenDefined = (tag) => customElements.whenDefined(tag);
  await Promise.race([whenDefined("ha-card"), whenDefined("ha-panel-lovelace")]);

  const LitElement = window.LitElement || Object.getPrototypeOf(customElements.get("ha-card"));
  const html = LitElement.prototype.html;
  const css = LitElement.prototype.css;

  class QWeatherMoreInfo extends LitElement {
    static get properties() {
      return {
        hass: { type: Object },
        stateObj: { type: Object }
      };
    }

    static get styles() {
      return css`
        :host {
          display: block;
          padding: 0 16px 20px 16px;
          color: var(--primary-text-color);
        }

        /* 顶部区块 */
        .header-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 20px 0;
        }
        .main-info { display: flex; align-items: center; }
        .weather-icon {
          width: 56px; height: 56px;
          background-size: contain;
          margin-right: 16px;
          background-repeat: no-repeat;
        }
        .state-text { font-size: 24px; font-weight: 500; }
        .temp-text { font-size: 42px; font-weight: 300; }
        .temp-text sup { font-size: 18px; }

        /* 核心属性网格 (2x2) */
        .attr-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 12px;
          margin-bottom: 24px;
        }
        .attr-item {
          background: var(--secondary-background-color);
          padding: 10px 14px;
          border-radius: 10px;
          display: flex;
          align-items: center;
        }
        .attr-item ha-icon { margin-right: 12px; color: var(--primary-color); --mdc-icon-size: 20px; }
        .attr-label { font-size: 11px; color: var(--secondary-text-color); }
        .attr-value { font-size: 14px; font-weight: 500; }

        /* 生活指数列表样式 */
        .suggestion-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        .suggestion-row {
          padding: 12px;
          border-radius: 8px;
          border-left: 4px solid var(--primary-color);
          background: var(--secondary-background-color);
        }
        .s-header {
          display: flex;
          justify-content: space-between;
          margin-bottom: 6px;
          font-weight: bold;
        }
        .s-name { color: var(--primary-text-color); font-size: 14px; }
        .s-brf { color: var(--primary-color); font-size: 14px; }
        .s-text {
          color: var(--secondary-text-color);
          font-size: 12px;
          line-height: 1.4;
          display: block;
        }

        .update-time {
          text-align: center;
          font-size: 10px;
          color: var(--secondary-text-color);
          margin-top: 20px;
          opacity: 0.7;
        }
      `;
    }

    _getIcon(code) {
      return `/qweather-local/qweather-card/icons/${code || '100'}.svg`;
    }

    render() {
      if (!this.stateObj) return html``;
      const attr = this.stateObj.attributes;

      // AQI 数据处理
      const aqiVal = attr.aqi?.aqi || attr.aqi || '--';
      const aqiCat = attr.aqi?.category || '';

      // 指数筛选
      const primaryTypes = ["comf", "drsg", "uv", "sport", "flu", "cw", "dc", "trav"];
      const suggestions = (attr.suggestion || [])
        .filter(s => primaryTypes.includes(s.type))
        .slice(0, 8);

      return html`
        <!-- 1. 顶部状态 -->
        <div class="header-row">
          <div class="main-info">
            <div class="weather-icon" style="background-image: url(${this._getIcon(attr.qweather_icon)})"></div>
            <div class="state-text">${attr.condition_cn || this.stateObj.state}</div>
          </div>
          <div class="temp-text">${Math.round(attr.temperature)}<sup>°C</sup></div>
        </div>

        <!-- 2. 核心属性网格 -->
        <div class="attr-grid">
          ${this._renderAttr('mdi:water-percent', '湿度', `${attr.humidity}%`)}
          ${this._renderAttr('mdi:gauge', '气压', `${attr.pressure} hPa`)}
          ${this._renderAttr('mdi:weather-windy', '风速', `${attr.wind_speed} km/h`)}
          ${this._renderAttr('mdi:air-filter', '空气质量', `${aqiVal} ${aqiCat}`)}
        </div>

        <!-- 3. 生活指数列表 -->
        <div class="suggestion-list">
          ${suggestions.length === 0 ? html`<div style="text-align:center; opacity:0.5">暂无指数数据</div>` : ''}
          ${suggestions.map(s => html`
            <div class="suggestion-row">
              <div class="s-header">
                <span class="s-name">${s.title_cn || s.title}</span>
                <span class="s-brf">${s.brf}</span>
              </div>
              <span class="s-text">${s.txt || s.text}</span>
            </div>
          `)}
        </div>

        <!-- 4. 页脚更新时间 -->
        <div class="update-time">
          数据源: QWeather | 更新于: ${attr.update_time || '刚刚'}
        </div>
      `;
    }

    _renderAttr(icon, label, value) {
      return html`
        <div class="attr-item">
          <ha-icon .icon=${icon}></ha-icon>
          <div>
            <div class="attr-label">${label}</div>
            <div class="attr-value">${value}</div>
          </div>
        </div>
      `;
    }
  }

  if (!customElements.get('qweather-more-info')) {
    customElements.define('qweather-more-info', QWeatherMoreInfo);
  }
})();
