const TRANSLATIONS_URL = '/egddistribuce_card/hdo_card_translations';
const DEFAULT_LANGUAGE = 'en';
const translationCache = new Map();

async function fetchTranslations(language) {
  try {
    const response = await fetch(`${TRANSLATIONS_URL}/${language}.json`);
    return response.ok ? await response.json() : {};
  } catch (err) {
    return {};
  }
}

// Translations are loaded once per language and shared by all card instances; missing keys fall back to English
function loadTranslations(language) {
  if (!translationCache.has(language)) {
    translationCache.set(language, (async () => {
      const fallback = await fetchTranslations(DEFAULT_LANGUAGE);
      if (language === DEFAULT_LANGUAGE) {
        return fallback;
      }
      return { ...fallback, ...(await fetchTranslations(language)) };
    })());
  }
  return translationCache.get(language);
}

class HdoChartCard extends HTMLElement {
  _locale() {
    const locale = this._hass?.locale?.language || DEFAULT_LANGUAGE;
    try {
      return Intl.getCanonicalLocales(locale)[0];
    } catch (err) {
      return DEFAULT_LANGUAGE;
    }
  }

  _language() {
    const language = this._locale().split('-')[0].toLowerCase();
    return /^[a-z]{2,3}$/.test(language) ? language : DEFAULT_LANGUAGE;
  }

  _t(key) {
    return this._translations?.[key] ?? key;
  }

  set hass(hass) {
    this._hass = hass;

    const language = this._language();
    if (this._translationsLanguage !== language) {
      this._translationsLanguage = language;
      this._translations = null;
      loadTranslations(language).then((translations) => {
        if (this._translationsLanguage === language) {
          this._translations = translations;
          this.hass = this._hass;
        }
      });
    }
    if (!this._translations) {
      return;
    }

    if (!this.content) {
      const card = document.createElement('ha-card');
      // Nastavit header pouze pokud show_header není false
      if (this.config.show_header !== false) {
        card.header = this.config.title || 'HDO Timeline';
      }
      this.content = document.createElement('div');
      this.content.style.padding = '16px';
      card.appendChild(this.content);
      this.appendChild(card);
    }

    const entityId = this.config.entity;
    const stateObj = hass.states[entityId];
    
    if (!stateObj) {
      this.content.innerHTML = `<p>Entity ${entityId} not found</p>`;
      return;
    }


    const hdoHourly = stateObj.attributes['HDO_HOURLY'] 
                   || stateObj.attributes['HDO HOURLY']
                   || stateObj.attributes['hdo_hourly'];
    
    if (!hdoHourly) {
      this.content.innerHTML = '<p>HDO_HOURLY attribute not found</p>';
      return;
    }
    

    if (typeof hdoHourly === 'string') {
      this.content.innerHTML = '<p>HDO_HOURLY is a string, not an object. Check binary_sensor.py</p>';
      return;
    }
    
    if (typeof hdoHourly !== 'object') {
      this.content.innerHTML = `<p>HDO_HOURLY has unexpected type: ${typeof hdoHourly}</p>`;
      return;
    }
    
    const keys = Object.keys(hdoHourly);
    if (keys.length === 0) {
      this.content.innerHTML = '<p>HDO_HOURLY is empty (no data)</p>';
      return;
    }

    const hdoData = this._parseHdoData(hdoHourly);
    const showDays = this.config.show_days || 1; 
    
    this.content.innerHTML = this._renderChart(hdoData, showDays, stateObj.attributes);
    this._startCountdown(stateObj.attributes.next_change);
  }

  _startCountdown(nextChangeIso) {
    this._nextChange = nextChangeIso ? new Date(nextChangeIso) : null;
    if (this._countdownTimer) {
      return;
    }
    // The attribute doesn't change every minute, so the countdown ticks in the browser
    this._countdownTimer = setInterval(() => {
      const el = this.querySelector('.hdo-remaining');
      if (el) {
        el.textContent = this._formatRemaining(this._nextChange);
      }
    }, 15000);
  }

  disconnectedCallback() {
    if (this._countdownTimer) {
      clearInterval(this._countdownTimer);
      this._countdownTimer = null;
    }
  }

  _parseHdoData(hdoHourly) {
    const entries = [];
    
    for (const [timestamp, price] of Object.entries(hdoHourly)) {
      const dt = new Date(timestamp);
      entries.push({
        timestamp: dt,
        price: parseFloat(price),
        hour: dt.getHours() + dt.getMinutes() / 60
      });
    }
    
    entries.sort((a, b) => a.timestamp - b.timestamp);
    
    return entries;
  }

  _renderChart(hdoData, showDays, attributes) {
    const priceVt = parseFloat(attributes.price_vt || 7.0);
    const priceNt = parseFloat(attributes.price_nt || 3.0);
    const colorVt = attributes.color_vt || '#ff5252';
    const colorNt = attributes.color_nt || '#2196f3';
    this._priceUnit = this._escapeHtml(attributes.price_unit || 'Kč/kWh');
    
    const nextChange = attributes.next_change ? new Date(attributes.next_change) : null;
    const remainingTime = this._formatRemaining(nextChange);

    const hdoTimesToday = attributes.hdo_times_today_raw || [];
    const hdoTimesTomorrow = attributes.hdo_times_tomorrow_raw || [];
    const region = attributes.region || '';
    const isTou = region === 'TOU';
    
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    let html = '<div style="width: 100%;">';
    

    if (showDays >= 1) {
      const dayLabel = this._t('today');
      const dateStr = today.toLocaleDateString(this._locale(), { weekday: 'short', day: 'numeric', month: 'short' });
      
      html += `
        <div style="margin-bottom: 24px;">
          <div style="font-weight: 500; margin-bottom: 8px; color: var(--primary-text-color);">
            ${dayLabel} (${dateStr})
          </div>
          ${this._renderDayChartFromSlots(hdoTimesToday, priceVt, priceNt, colorVt, colorNt, isTou, true)}
        </div>
      `;
    }
    
 
    if (showDays >= 2) {
      const tomorrow = new Date(today);
      tomorrow.setDate(tomorrow.getDate() + 1);
      const dayLabel = this._t('tomorrow');
      const dateStr = tomorrow.toLocaleDateString(this._locale(), { weekday: 'short', day: 'numeric', month: 'short' });
      
      html += `
        <div style="margin-bottom: 24px;">
          <div style="font-weight: 500; margin-bottom: 8px; color: var(--primary-text-color);">
            ${dayLabel} (${dateStr})
          </div>
          ${this._renderDayChartFromSlots(hdoTimesTomorrow, priceVt, priceNt, colorVt, colorNt, isTou, false)}
        </div>
      `;
    }
    
    html += this._renderLegend(priceVt, priceNt, colorVt, colorNt, remainingTime);
    html += '</div>';
    
    return html;
  }

  _groupByDay(hdoData) {
    const groups = {};
    
    for (const entry of hdoData) {
      const dateKey = entry.timestamp.toISOString().split('T')[0];
      if (!groups[dateKey]) {
        groups[dateKey] = [];
      }
      groups[dateKey].push(entry);
    }
    
    return Object.keys(groups).map(date => ({
      date,
      entries: groups[date]
    })).sort((a, b) => a.date.localeCompare(b.date));
  }

  _renderDayChartFromSlots(hdoSlots, priceVt, priceNt, colorVt, colorNt, isTou, isToday) {

    const parsedSlots = [];
    for (const slot of hdoSlots) {
      try {
        const startParts = slot.od.split(':');
        const endParts = slot.do.split(':');
        const startHour = parseInt(startParts[0]) + parseInt(startParts[1]) / 60;
        let endHour = parseInt(endParts[0]) + parseInt(endParts[1]) / 60;
        

        if (slot.do === '23:59:00') {
          endHour = 24;
        }
        
        parsedSlots.push({ start: startHour, end: endHour });
      } catch (e) {
        console.error('Error parsing slot:', slot, e);
      }
    }
    

    parsedSlots.sort((a, b) => a.start - b.start);
    

    const mergedSlots = [];
    for (const slot of parsedSlots) {
      if (mergedSlots.length === 0) {
        mergedSlots.push({ start: slot.start, end: slot.end });
      } else {
        const lastSlot = mergedSlots[mergedSlots.length - 1];
        

        if (slot.start <= lastSlot.end) {
          lastSlot.end = Math.max(lastSlot.end, slot.end);
        } else {

          mergedSlots.push({ start: slot.start, end: slot.end });
        }
      }
    }
    

    const blocks = [];
    let currentTime = 0;
    
    for (const slot of mergedSlots) {

      if (currentTime < slot.start) {
        blocks.push({
          isVt: true,
          start: currentTime,
          end: slot.start,
          price: priceVt
        });
      }
      

      blocks.push({
        isVt: false,
        start: slot.start,
        end: slot.end,
        price: priceNt
      });
      
      currentTime = slot.end;
    }
    

    if (currentTime < 24) {
      blocks.push({
        isVt: true,
        start: currentTime,
        end: 24,
        price: priceVt
      });
    }
    

    let html = `
      <div style="position: relative; height: 40px; background: var(--divider-color); border-radius: 4px; overflow: hidden;">
    `;
    
    for (const block of blocks) {
      const left = (block.start / 24) * 100;
      const width = ((block.end - block.start) / 24) * 100;
      const color = block.isVt ? colorVt : colorNt;
      const label = block.isVt ? this._t('high_tariff_short') : this._t('low_tariff_short');
      const startTime = this._formatHour(block.start);
      const endTime = this._formatHour(block.end);
      const title = this._escapeHtml(`${label}: ${startTime} - ${endTime} (${block.price} ${this._priceUnit})`);

      html += `
        <div style="
          position: absolute;
          left: ${left}%;
          width: ${width}%;
          height: 100%;
          background: ${color};
          display: flex;
          align-items: center;
          justify-content: center;
          color: white;
          font-size: 11px;
          font-weight: 500;
          cursor: pointer;
          transition: opacity 0.2s;
        "
        title="${title}"
        onmouseover="this.style.opacity='0.8'"
        onmouseout="this.style.opacity='1'">
          ${width > 8 ? label : ''}
        </div>
      `;
    }
    

    if (isToday) {
      const now = new Date();
      const currentHour = now.getHours() + now.getMinutes() / 60;
      const currentPosition = (currentHour / 24) * 100;
      
      html += `
        <div style="
          position: absolute;
          left: ${currentPosition}%;
          top: 0;
          bottom: 0;
          width: 2px;
          background: rgba(255, 255, 255, 0.9);
          box-shadow: 0 0 4px rgba(0, 0, 0, 0.5);
          z-index: 3;
        "
        title="${this._t('current_time')}: ${this._formatHour(currentHour)}">
        </div>
      `;
    }
    
    html += '</div>';
    

    html += `
      <div style="display: flex; justify-content: space-between; margin-top: 4px; font-size: 10px; color: var(--secondary-text-color);">
        <span>0:00</span>
        <span>6:00</span>
        <span>12:00</span>
        <span>18:00</span>
        <span>24:00</span>
      </div>
    `;
    
    return html;
  }

  _renderDayChart(dayEntries, priceVt, priceNt, colorVt, colorNt, isToday = false) {
    if (dayEntries.length === 0) {
      return '<p>No data for this day</p>';
    }
    

    const blocks = [];
    let currentBlock = null;
    
    for (let i = 0; i < dayEntries.length; i++) {
      const entry = dayEntries[i];
      const isVt = Math.abs(entry.price - priceVt) < 0.01;
      
      if (!currentBlock || currentBlock.isVt !== isVt) {
        if (currentBlock) {
          blocks.push(currentBlock);
        }
        currentBlock = {
          isVt,
          start: entry.hour,
          end: entry.hour + 0.25, 
          price: entry.price
        };
      } else {
        currentBlock.end = entry.hour + 0.25;
      }
    }
    
    if (currentBlock) {
      blocks.push(currentBlock);
    }
    

    if (blocks.length > 0 && blocks[0].start > 0) {
      blocks[0].start = 0;
    }
    

    if (blocks.length > 0 && blocks[blocks.length - 1].end < 24) {
      blocks[blocks.length - 1].end = 24;
    }
    

    let html = `
      <div style="position: relative; height: 40px; background: var(--divider-color); border-radius: 4px; overflow: hidden;">
    `;
    
    for (const block of blocks) {
      const left = (block.start / 24) * 100;
      const width = ((block.end - block.start) / 24) * 100;
      const color = block.isVt ? colorVt : colorNt;
      const label = block.isVt ? this._t('high_tariff_short') : this._t('low_tariff_short');
      const startTime = this._formatHour(block.start);
      const endTime = this._formatHour(block.end);
      const title = this._escapeHtml(`${label}: ${startTime} - ${endTime} (${block.price} ${this._priceUnit})`);
      
      html += `
        <div style="
          position: absolute;
          left: ${left}%;
          width: ${width}%;
          height: 100%;
          background: ${color};
          display: flex;
          align-items: center;
          justify-content: center;
          color: white;
          font-size: 11px;
          font-weight: 500;
          cursor: pointer;
          transition: opacity 0.2s;
        "
        title="${title}"
        onmouseover="this.style.opacity='0.8'"
        onmouseout="this.style.opacity='1'">
          ${width > 8 ? label : ''}
        </div>
      `;
    }
    

    if (isToday) {
      const now = new Date();
      const currentHour = now.getHours() + now.getMinutes() / 60;
      const currentPosition = (currentHour / 24) * 100;
      
      html += `
        <div style="
          position: absolute;
          left: ${currentPosition}%;
          top: 0;
          bottom: 0;
          width: 2px;
          background: rgba(255, 255, 255, 0.9);
          box-shadow: 0 0 4px rgba(0, 0, 0, 0.5);
          z-index: 3;
        "
        title="${this._t('current_time')}: ${this._formatHour(currentHour)}">
        </div>
      `;
    }
    
    html += '</div>';
    

    html += `
      <div style="display: flex; justify-content: space-between; margin-top: 4px; font-size: 10px; color: var(--secondary-text-color);">
        <span>0:00</span>
        <span>6:00</span>
        <span>12:00</span>
        <span>18:00</span>
        <span>24:00</span>
      </div>
    `;
    
    return html;
  }

  _formatHour(hour) {
    const h = Math.floor(hour);
    const m = Math.round((hour - h) * 60);
    return `${h}:${m.toString().padStart(2, '0')}`;
  }

  _escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  _formatRemaining(target) {
    if (!target || isNaN(target)) {
      return '-';
    }
    const totalMinutes = Math.max(0, Math.floor((target - new Date()) / 60000));
    const hours = Math.floor(totalMinutes / 60);
    const minutes = String(totalMinutes % 60).padStart(2, '0');
    return `${hours}:${minutes}`;
  }

  _renderLegend(priceVt, priceNt, colorVt, colorNt, remainingTime) {
    return `
      <div style="display: flex; gap: 16px; margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--divider-color); font-size: 12px;">
        <div style="display: flex; align-items: center; gap: 6px;">
          <div style="width: 16px; height: 16px; background: ${colorVt}; border-radius: 2px;"></div>
          <span>${this._t('high_tariff_short')} (${priceVt} ${this._priceUnit})</span>
        </div>
        <div style="display: flex; align-items: center; gap: 6px;">
          <div style="width: 16px; height: 16px; background: ${colorNt}; border-radius: 2px;"></div>
          <span>${this._t('low_tariff_short')} (${priceNt} ${this._priceUnit})</span>
        </div>
        <div style="display: flex; align-items: center; gap: 6px;">
          <span>${this._t('next_change_in')}: <span class="hdo-remaining">${remainingTime}</span></span>
        </div>
      </div>
    `;
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error('You need to define an entity');
    }
    this.config = config;
  }

  getCardSize() {
    return 3;
  }

  static getConfigElement() {
    return document.createElement("hdo-chart-card-editor");
  }

  static getStubConfig() {
    return {
      entity: "binary_sensor.hdo_status",
      title: "HDO Timeline",
      show_days: 2,
      show_header: true
    };
  }
}

customElements.define('hdo-chart-card', HdoChartCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'hdo-chart-card',
  name: 'HDO Chart Card',
  description: 'Display HDO timeline as horizontal bar chart',
  preview: false,
  documentationURL: 'https://github.com/Antrac1t/HomeAssistant-EGDdistribuce'
});

console.info(
  '%c HDO-CHART-CARD %c v1.0.0 ',
  'color: white; background: #2196f3; font-weight: 700;',
  'color: white; background: #424242; font-weight: 700;'
);
