// HDO timeline card built on native HA building blocks:
// <ha-card>, theme CSS variables, scoped shadow DOM, getConfigForm (ha-form editor) and getGridOptions.
// It builds DOM with textContent/setAttribute only, so no HTML escaping is needed.
(() => {
  const CARD_VERSION = '1.1.0';
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

  const STYLE = `
    :host { display: block; }
    .day { margin-bottom: 24px; }
    .day-title { font-weight: 500; margin-bottom: 8px; color: var(--primary-text-color); }
    .bar {
      position: relative;
      height: 40px;
      background: var(--divider-color);
      border-radius: 4px;
      overflow: hidden;
    }
    .block {
      position: absolute;
      top: 0;
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      color: white;
      font-size: 11px;
      font-weight: 500;
      cursor: pointer;
      transition: opacity 0.2s;
      outline: none;
    }
    .block:hover, .block:focus-visible, .block.selected { opacity: 0.8; }
    .block.selected { box-shadow: inset 0 0 0 2px var(--primary-text-color); }
    .track { position: relative; }
    .track.has-now { padding-top: 24px; }
    .now {
      position: absolute;
      top: 0;
      bottom: 0;
      width: 0;
      z-index: 3;
      pointer-events: none;
    }
    .now-label {
      position: absolute;
      z-index: 1;
      top: 0;
      left: 0;
      transform: translateX(var(--shift, -50%));
      padding: 1px 7px;
      border-radius: 10px;
      font-size: 10px;
      font-weight: 600;
      line-height: 14px;
      white-space: nowrap;
      background: var(--primary-text-color);
      color: var(--card-background-color);
    }
    .now-line {
      position: absolute;
      top: 15px;
      bottom: 0;
      left: -1px;
      width: 2px;
      background: var(--primary-text-color);
      box-shadow: 0 0 0 1px var(--card-background-color);
    }
    .axis {
      display: flex;
      justify-content: space-between;
      margin-top: 4px;
      font-size: 10px;
      color: var(--secondary-text-color);
    }
    .content { position: relative; padding: 16px; }
    .tip {
      position: absolute;
      z-index: 4;
      top: 0;
      left: 0;
      width: max-content;
      max-width: 100%;
      box-sizing: border-box;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 12px;
      line-height: 18px;
      background: var(--primary-text-color);
      color: var(--card-background-color);
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
      pointer-events: none;
    }
    .tip[hidden] { display: none; }
    .legend {
      display: flex;
      flex-wrap: wrap;
      gap: 8px 16px;
      padding-top: 16px;
      border-top: 1px solid var(--divider-color);
      font-size: 12px;
      color: var(--primary-text-color);
    }
    .legend-item { display: flex; align-items: center; gap: 6px; }
    .swatch { width: 16px; height: 16px; border-radius: 2px; }
    .message { padding: 16px; margin: 0; }
  `;

  const FORM_LABELS = {
    entity: 'Entity',
    title: 'Title',
    show_header: 'Show header',
    show_days: 'Days to show',
  };

  class HdoChartCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' });
      this._pinned = null;
      this._blocks = new Map();
    }

    setConfig(config) {
      if (!config.entity) {
        throw new Error('You need to define an entity');
      }
      this._config = config;
      this._stateObj = undefined;
      this._update();
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
            this._stateObj = undefined;
            this._update();
          }
        });
      }
      this._update();
    }

    connectedCallback() {
      this._inView = true;
      // The marker only needs to move while the card is on screen and the tab is active
      this._observer = new IntersectionObserver(([entry]) => {
        this._inView = entry.isIntersecting;
        this._syncTimer();
      });
      this._observer.observe(this);
      this._onVisibility = () => this._syncTimer();
      document.addEventListener('visibilitychange', this._onVisibility);
      // A tap or click anywhere but on a block (also outside the card) dismisses the pinned tooltip
      this._onOutsidePress = (event) => {
        if (this._pinned && !event.composedPath().some((node) => node.classList?.contains('block'))) {
          this._pinned = null;
          this._restoreTip();
        }
      };
      this._onEscape = (event) => {
        if (event.key === 'Escape' && this._pinned) {
          this._pinned = null;
          this._restoreTip();
        }
      };
      document.addEventListener('pointerdown', this._onOutsidePress);
      document.addEventListener('keydown', this._onEscape);
      this._syncTimer();
    }

    disconnectedCallback() {
      this._observer?.disconnect();
      document.removeEventListener('visibilitychange', this._onVisibility);
      document.removeEventListener('pointerdown', this._onOutsidePress);
      document.removeEventListener('keydown', this._onEscape);
      this._inView = false;
      this._syncTimer();
    }

    // Runs one tick at every minute boundary instead of polling; catches up immediately when it resumes
    _syncTimer() {
      clearTimeout(this._timer);
      this._timer = null;
      if (!this._inView || document.hidden) {
        return;
      }
      this._tick();
      const toNextMinute = 60000 - (Date.now() % 60000);
      this._timer = setTimeout(() => this._syncTimer(), toNextMinute + 100);
    }

    getCardSize() {
      return 3;
    }

    // Sections view: 12 columns wide, height follows the content
    getGridOptions() {
      return { columns: 12, min_columns: 6, rows: 'auto' };
    }

    static getConfigForm() {
      return {
        schema: [
          { name: 'entity', required: true, selector: { entity: { domain: 'binary_sensor', integration: 'egddistribuce' } } },
          { name: 'title', selector: { text: {} } },
          { name: 'show_header', selector: { boolean: {} } },
          { name: 'show_days', selector: { number: { min: 1, max: 2, mode: 'box' } } },
        ],
        computeLabel: (schema) => FORM_LABELS[schema.name] || schema.name,
      };
    }

    static getStubConfig() {
      return { entity: 'binary_sensor.hdo_status', title: 'HDO Timeline', show_days: 2, show_header: true };
    }

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

    _update() {
      if (!this._config || !this._hass || !this._translations) {
        return;
      }
      // HA hands out a new state object only when the entity changed
      const stateObj = this._hass.states[this._config.entity];
      if (stateObj && stateObj === this._stateObj) {
        return;
      }
      this._stateObj = stateObj;
      this._render(stateObj);
    }

    _render(stateObj) {
      const style = document.createElement('style');
      style.textContent = STYLE;
      const card = document.createElement('ha-card');
      if (this._config.show_header !== false) {
        card.header = this._config.title || 'HDO Timeline';
      }

      const attrs = stateObj?.attributes;
      if (!attrs || !Array.isArray(attrs.hdo_times_today_raw)) {
        const message = document.createElement('p');
        message.className = 'message';
        message.textContent = stateObj
          ? 'hdo_times_today_raw attribute not found'
          : `Entity ${this._config.entity} not found`;
        card.appendChild(message);
        this.shadowRoot.replaceChildren(style, card);
        return;
      }

      const priceVt = parseFloat(attrs.price_vt || 7.0);
      const priceNt = parseFloat(attrs.price_nt || 3.0);
      this._colors = {
        vt: attrs.color_vt || 'var(--error-color, #ff5252)',
        nt: attrs.color_nt || 'var(--info-color, #2196f3)',
      };
      this._priceUnit = attrs.price_unit || 'Kč/kWh';
      this._nextChange = attrs.next_change ? new Date(attrs.next_change) : null;

      const content = document.createElement('div');
      content.className = 'content';
      this._content = content;
      this._blocks = new Map();

      const today = new Date();
      today.setHours(0, 0, 0, 0);
      const days = [{ key: 'today', date: today, slots: attrs.hdo_times_today_raw, isToday: true }];
      if ((this._config.show_days || 1) >= 2) {
        const tomorrow = new Date(today);
        tomorrow.setDate(tomorrow.getDate() + 1);
        days.push({ key: 'tomorrow', date: tomorrow, slots: attrs.hdo_times_tomorrow_raw || [], isToday: false });
      }

      this._nowMarker = null;
      for (const day of days) {
        content.appendChild(this._renderDay(day, priceVt, priceNt));
      }
      content.appendChild(this._renderLegend(priceVt, priceNt));

      // One shared tooltip for hover, keyboard focus and touch
      this._tipEl = document.createElement('div');
      this._tipEl.className = 'tip';
      this._tipEl.setAttribute('role', 'tooltip');
      this._tipEl.hidden = true;
      content.appendChild(this._tipEl);

      card.appendChild(content);
      this.shadowRoot.replaceChildren(style, card);
      if (this._pinned && !this._blocks.has(this._pinned)) {
        this._pinned = null;
      }
      this._restoreTip();
      this._tick();
    }

    _showTip(id) {
      const entry = this._blocks.get(id);
      if (!entry || !this._tipEl) {
        return;
      }
      const tip = this._tipEl;
      tip.textContent = entry.text;
      tip.hidden = false;
      const area = this._content.getBoundingClientRect();
      const anchor = entry.el.getBoundingClientRect();
      const size = tip.getBoundingClientRect();
      const left = anchor.left - area.left + anchor.width / 2 - size.width / 2;
      tip.style.left = `${Math.max(0, Math.min(left, area.width - size.width))}px`;
      const above = anchor.top - area.top - size.height - 6;
      tip.style.top = `${above >= 0 ? above : anchor.bottom - area.top + 6}px`;
    }

    // Shows the pinned block's tooltip, or hides it when nothing is pinned
    _restoreTip() {
      for (const [id, entry] of this._blocks) {
        entry.el.classList.toggle('selected', id === this._pinned);
      }
      if (this._pinned) {
        this._showTip(this._pinned);
      } else if (this._tipEl) {
        this._tipEl.hidden = true;
      }
    }

    _renderDay(day, priceVt, priceNt) {
      const wrapper = document.createElement('div');
      wrapper.className = 'day';

      const dateStr = day.date.toLocaleDateString(this._locale(), { weekday: 'short', day: 'numeric', month: 'short' });
      const title = document.createElement('div');
      title.className = 'day-title';
      title.textContent = `${this._t(day.key)} (${dateStr})`;
      wrapper.appendChild(title);

      const track = document.createElement('div');
      track.className = 'track';
      const bar = document.createElement('div');
      bar.className = 'bar';
      this._buildBlocks(day.slots, priceVt, priceNt).forEach((block, index) => {
        bar.appendChild(this._renderBlock(block, `${day.key}-${index}`));
      });
      track.appendChild(bar);

      if (day.isToday) {
        // Lives outside the bar (which clips its content) so the time label can sit above it
        track.classList.add('has-now');
        this._nowMarker = document.createElement('div');
        this._nowMarker.className = 'now';
        const line = document.createElement('div');
        line.className = 'now-line';
        this._nowLabel = document.createElement('div');
        this._nowLabel.className = 'now-label';
        this._nowMarker.append(line, this._nowLabel);
        track.appendChild(this._nowMarker);
      }
      wrapper.appendChild(track);

      const axis = document.createElement('div');
      axis.className = 'axis';
      for (const hour of [0, 6, 12, 18, 24]) {
        const label = document.createElement('span');
        label.textContent = `${hour}:00`;
        axis.appendChild(label);
      }
      wrapper.appendChild(axis);
      return wrapper;
    }

    _renderBlock(block, id) {
      const label = block.isVt ? this._t('high_tariff_short') : this._t('low_tariff_short');
      const width = ((block.end - block.start) / 24) * 100;
      const text = `${label}: ${this._formatHour(block.start)} - ${this._formatHour(block.end)} (${block.price} ${this._priceUnit})`;

      const el = document.createElement('div');
      el.className = 'block';
      el.style.left = `${(block.start / 24) * 100}%`;
      el.style.width = `${width}%`;
      el.style.background = block.isVt ? this._colors.vt : this._colors.nt;
      el.textContent = width > 8 ? label : '';
      el.tabIndex = 0;
      el.setAttribute('role', 'button');
      el.setAttribute('aria-label', text);
      this._blocks.set(id, { el, text });

      // Tap/click/Enter pins the tooltip; touch has no hover, so pinning is the only way to see it there
      const toggle = (keepVisible) => {
        const unpin = this._pinned === id;
        this._pinned = unpin ? null : id;
        this._restoreTip();
        if (unpin && keepVisible) {
          this._showTip(id);
        }
      };
      el.addEventListener('click', (event) => toggle(event.pointerType === 'mouse'));
      el.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          toggle(true);
        }
      });
      // Mouse hover only: touch pointers also fire pointerenter, which would show a tip that never hides
      el.addEventListener('pointerenter', (event) => {
        if (event.pointerType === 'mouse') {
          this._showTip(id);
        }
      });
      el.addEventListener('pointerleave', (event) => {
        if (event.pointerType === 'mouse') {
          this._restoreTip();
        }
      });
      el.addEventListener('focus', () => this._showTip(id));
      el.addEventListener('blur', () => this._restoreTip());
      return el;
    }

    // Merges the low-tariff slots and fills the gaps between them with high-tariff blocks
    _buildBlocks(rawSlots, priceVt, priceNt) {
      const toHour = (value) => {
        const [h, m] = value.split(':').map(Number);
        return h + m / 60;
      };
      const slots = rawSlots
        .map((slot) => ({ start: toHour(slot.od), end: slot.do === '23:59:00' ? 24 : toHour(slot.do) }))
        .filter((slot) => !isNaN(slot.start) && !isNaN(slot.end))
        .sort((a, b) => a.start - b.start);

      const merged = [];
      for (const slot of slots) {
        const last = merged[merged.length - 1];
        if (last && slot.start <= last.end) {
          last.end = Math.max(last.end, slot.end);
        } else {
          merged.push({ ...slot });
        }
      }

      const blocks = [];
      let cursor = 0;
      for (const slot of merged) {
        if (cursor < slot.start) {
          blocks.push({ isVt: true, start: cursor, end: slot.start, price: priceVt });
        }
        blocks.push({ isVt: false, start: slot.start, end: slot.end, price: priceNt });
        cursor = slot.end;
      }
      if (cursor < 24) {
        blocks.push({ isVt: true, start: cursor, end: 24, price: priceVt });
      }
      return blocks;
    }

    _renderLegend(priceVt, priceNt) {
      const legend = document.createElement('div');
      legend.className = 'legend';

      const item = (color, text) => {
        const el = document.createElement('div');
        el.className = 'legend-item';
        if (color) {
          const swatch = document.createElement('div');
          swatch.className = 'swatch';
          swatch.style.background = color;
          el.appendChild(swatch);
        }
        const span = document.createElement('span');
        span.textContent = text;
        el.appendChild(span);
        return el;
      };

      legend.appendChild(item(this._colors.vt, `${this._t('high_tariff_short')} (${priceVt} ${this._priceUnit})`));
      legend.appendChild(item(this._colors.nt, `${this._t('low_tariff_short')} (${priceNt} ${this._priceUnit})`));

      const next = item(null, `${this._t('next_change_in')}: `);
      this._remainingEl = document.createElement('span');
      next.firstChild.appendChild(this._remainingEl);
      legend.appendChild(next);
      return legend;
    }

    // Moves the current-time marker and the countdown without re-rendering
    _tick() {
      if (this._nowMarker) {
        const now = new Date();
        const hour = now.getHours() + now.getMinutes() / 60;
        const percent = (hour / 24) * 100;
        this._nowMarker.style.left = `${percent}%`;
        // Keeps the label inside the card near the edges
        this._nowMarker.style.setProperty('--shift', percent < 6 ? '-10%' : percent > 94 ? '-90%' : '-50%');
        this._nowLabel.textContent = this._formatHour(hour);
      }
      if (this._remainingEl) {
        this._remainingEl.textContent = this._formatRemaining(this._nextChange);
      }
    }

    _formatHour(hour) {
      const h = Math.floor(hour);
      const m = Math.round((hour - h) * 60);
      return `${h}:${String(m).padStart(2, '0')}`;
    }

    _formatRemaining(target) {
      if (!target || isNaN(target)) {
        return '-';
      }
      const totalMinutes = Math.max(0, Math.floor((target - new Date()) / 60000));
      return `${Math.floor(totalMinutes / 60)}:${String(totalMinutes % 60).padStart(2, '0')}`;
    }
  }

  // Modules added by the integration run before the frontend installs its scoped custom element registry polyfill.
  // An element defined that early is invisible to the dashboard ("Custom element doesn't exist"), so wait for ha-card.
  customElements.whenDefined('ha-card').then(() => {
    if (customElements.get('egd-hdo-chart-card')) {
      return;
    }
    customElements.define('egd-hdo-chart-card', HdoChartCard);

    window.customCards = window.customCards || [];
    window.customCards.push({
      type: 'egd-hdo-chart-card',
      name: 'HDO Chart Card',
      description: 'Display HDO timeline as horizontal bar chart',
      preview: false,
      documentationURL: 'https://github.com/Antrac1t/HomeAssistant-EGDdistribuce',
    });

    console.info(
      `%c EGD-HDO-CHART-CARD %c v${CARD_VERSION}`,
      'color: white; background: #2196f3; font-weight: 700;',
      'color: white; background: #424242; font-weight: 700;'
    );
  });
})();
