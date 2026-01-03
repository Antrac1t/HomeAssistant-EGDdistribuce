class HdoChartCard extends HTMLElement {
  set hass(hass) {
    if (!this.content) {
      const card = document.createElement('ha-card');
      card.header = this.config.title || 'HDO Timeline';
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
    

    const hdoTimesToday = attributes.hdo_times_today_raw || [];
    const hdoTimesTomorrow = attributes.hdo_times_tomorrow_raw || [];
    const region = attributes.region || '';
    const isTou = region === 'TOU';
    
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    let html = '<div style="width: 100%;">';
    

    if (showDays >= 1) {
      const dayLabel = 'Dnes';
      const dateStr = today.toLocaleDateString('cs-CZ', { weekday: 'short', day: 'numeric', month: 'short' });
      
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
      const dayLabel = 'Zítra';
      const dateStr = tomorrow.toLocaleDateString('cs-CZ', { weekday: 'short', day: 'numeric', month: 'short' });
      
      html += `
        <div style="margin-bottom: 24px;">
          <div style="font-weight: 500; margin-bottom: 8px; color: var(--primary-text-color);">
            ${dayLabel} (${dateStr})
          </div>
          ${this._renderDayChartFromSlots(hdoTimesTomorrow, priceVt, priceNt, colorVt, colorNt, isTou, false)}
        </div>
      `;
    }
    
    html += this._renderLegend(priceVt, priceNt, colorVt, colorNt);
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
      const label = block.isVt ? 'VT' : 'NT';
      const startTime = this._formatHour(block.start);
      const endTime = this._formatHour(block.end);
      
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
        title="${label}: ${startTime} - ${endTime} (${block.price} Kč/kWh)"
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
          z-index: 10;
        "
        title="Aktuální čas: ${this._formatHour(currentHour)}">
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
      const label = block.isVt ? 'VT' : 'NT';
      const startTime = this._formatHour(block.start);
      const endTime = this._formatHour(block.end);
      
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
        title="${label}: ${startTime} - ${endTime} (${block.price} Kč/kWh)"
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
          z-index: 10;
        "
        title="Aktuální čas: ${this._formatHour(currentHour)}">
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

  _renderLegend(priceVt, priceNt, colorVt, colorNt) {
    return `
      <div style="display: flex; gap: 16px; margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--divider-color); font-size: 12px;">
        <div style="display: flex; align-items: center; gap: 6px;">
          <div style="width: 16px; height: 16px; background: ${colorVt}; border-radius: 2px;"></div>
          <span>VT (${priceVt} Kč/kWh)</span>
        </div>
        <div style="display: flex; align-items: center; gap: 6px;">
          <div style="width: 16px; height: 16px; background: ${colorNt}; border-radius: 2px;"></div>
          <span>NT (${priceNt} Kč/kWh)</span>
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
      show_days: 2
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
