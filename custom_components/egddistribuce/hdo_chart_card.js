// HDO timeline card built on native HA building blocks:
// <ha-card>, theme CSS variables, scoped shadow DOM, getConfigForm (ha-form editor) and getGridOptions.
// It builds DOM with textContent/setAttribute only, so no HTML escaping is needed.
(() => {
  const CARD_VERSION = '1.1.1';
  const TRANSLATIONS_URL = '/egddistribuce_card/hdo_card_translations';
  const DEFAULT_LANGUAGE = 'en';
  const LAST_MINUTE_OF_DAY = 24 * 60 - 1;
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
      pointer-events: auto;
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
      // Tooltip sources; the shown block is hovered ?? focused ?? pinned (see _activeId)
      this._pinned = null;
      this._hovered = null;
      this._focused = null;
      this._hoverTimer = null;
      this._blocks = new Map();
    }

    setConfig(config) {
      if (!config.entity) {
        throw new Error('You need to define an entity');
      }
      this._config = config;
      this._update(true);
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
            this._update(true);
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
      // A tap or click outside this card dismisses the pinned tooltip
      this._onOutsidePress = (event) => {
        // Blocks of other cards on the same dashboard count as outside
        const onOwnTarget = event.composedPath().some(
          (node) => (
            (node.classList?.contains('block') || node.classList?.contains('tip'))
            && node.getRootNode() === this.shadowRoot
          ),
        );
        if (this._pinned && !onOwnTarget) {
          this._pinned = null;
          this._restoreTip();
        }
      };
      // Also dismisses tooltips shown by hover or keyboard focus, which are never pinned
      this._onEscape = (event) => {
        if (event.key === 'Escape' && this._activeId()) {
          this._pinned = null;
          this._focused = null;
          this._hovered = null;
          this._clearHoverTimer();
          this._restoreTip();
        }
      };
      // Keeps a visible tooltip inside the card after rotation or dashboard resizing
      this._resizeObserver = new ResizeObserver(() => {
        const id = this._activeId();
        if (id) {
          this._showTip(id);
        }
      });
      if (this._content) {
        this._resizeObserver.observe(this._content);
      }
      document.addEventListener('pointerdown', this._onOutsidePress);
      document.addEventListener('keydown', this._onEscape);
      this._syncTimer();
    }

    disconnectedCallback() {
      this._observer?.disconnect();
      this._resizeObserver?.disconnect();
      this._resizeObserver = null;
      document.removeEventListener('visibilitychange', this._onVisibility);
      document.removeEventListener('pointerdown', this._onOutsidePress);
      document.removeEventListener('keydown', this._onEscape);
      this._clearHoverTimer();
      this._focused = null;
      this._hovered = null;
      this._inView = false;
      this._syncTimer();
    }

    // Current price sensor on the same device; hass.entities follows registry edits
    _findPriceEntityId() {
      const entities = this._hass.entities || {};
      const deviceId = entities[this._config.entity]?.device_id;
      const priceEntity = deviceId && Object.values(entities).find((entity) => (
        entity.device_id === deviceId
        && entity.platform === 'egddistribuce'
        && entity.translation_key === 'current_price'
      ));
      return priceEntity?.entity_id;
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

    // HA formats it like the price sensor: display precision, number format and unit
    _formatPrice(value) {
      const priceState = this._hass.states[this._priceEntityId];
      if (priceState) {
        return this._hass.formatEntityState(priceState, String(value));
      }
      const number = new Intl.NumberFormat('en', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
      return `${number} ${this._priceUnit}`;
    }

    _language() {
      const language = this._locale().split('-')[0].toLowerCase();
      return /^[a-z]{2,3}$/.test(language) ? language : DEFAULT_LANGUAGE;
    }

    _t(key) {
      return this._translations?.[key] ?? key;
    }

    // force: render even when the entity state is unchanged (new config or translations)
    _update(force = false) {
      if (!this._config || !this._hass || !this._translations) {
        return;
      }
      // HA hands out a new state object only when the entity changed
      const stateObj = this._hass.states[this._config.entity];
      // HA replaces hass.entities and hass.locale only when the registry or user settings changed
      const { entities, locale } = this._hass;
      const entitiesChanged = entities !== this._entities;
      if (entitiesChanged || this._priceSourceEntityId !== this._config.entity) {
        this._entities = entities;
        this._priceSourceEntityId = this._config.entity;
        this._priceEntityId = this._findPriceEntityId();
      }
      // Price formatting follows the price sensor state, which may arrive after the registry entry
      const priceState = this._hass.states[this._priceEntityId];
      if (!force && stateObj && stateObj === this._stateObj && !entitiesChanged
        && priceState === this._priceState && locale === this._localeData) {
        return;
      }
      this._stateObj = stateObj;
      this._priceState = priceState;
      this._localeData = locale;
      this._render(stateObj);
    }

    _render(stateObj) {
      const focusedId = this.shadowRoot.activeElement?.dataset.blockId;
      this._clearHoverTimer();
      this._hovered = null;

      const style = document.createElement('style');
      style.textContent = STYLE;
      const card = document.createElement('ha-card');
      if (this._config.show_header !== false) {
        card.header = this._config.title || 'HDO Timeline';
      }

      const attrs = stateObj?.attributes;
      if (!attrs || !Array.isArray(attrs.hdo_intervals) || !attrs.date_today) {
        const message = document.createElement('p');
        message.className = 'message';
        message.textContent = stateObj
          ? 'hdo_intervals or date_today attribute not found'
          : `Entity ${this._config.entity} not found`;
        card.appendChild(message);
        this.shadowRoot.replaceChildren(style, card);
        return;
      }

      // The integration always provides prices, colors and the unit
      const priceVt = parseFloat(attrs.price_vt);
      const priceNt = parseFloat(attrs.price_nt);
      this._colors = {
        vt: attrs.color_vt || 'var(--error-color, #ff5252)',
        nt: attrs.color_nt || 'var(--info-color, #2196f3)',
      };
      this._priceUnit = attrs.price_unit;
      this._nextChange = attrs.next_change ? new Date(attrs.next_change) : null;

      const content = document.createElement('div');
      content.className = 'content';
      this._content = content;
      this._blocks = new Map();
      this._resizeObserver?.disconnect();
      this._resizeObserver?.observe(content);

      // Days follow the date the backend computed the schedule for, not the browser's date,
      // so a browser in another time zone or with a skewed clock still shows the matching data
      const [year, month, dayOfMonth] = attrs.date_today.split('-').map(Number);
      const today = new Date(year, month - 1, dayOfMonth);
      const days = [{ key: 'today', date: today, isToday: true }];
      if ((this._config.show_days || 1) >= 2) {
        const tomorrow = new Date(today);
        tomorrow.setDate(tomorrow.getDate() + 1);
        days.push({ key: 'tomorrow', date: tomorrow, isToday: false });
      }

      this._nowMarker = null;
      for (const day of days) {
        content.appendChild(this._renderDay(day, attrs.hdo_intervals, priceVt, priceNt));
      }
      content.appendChild(this._renderLegend(priceVt, priceNt));

      // One shared tooltip for hover, keyboard focus and touch
      this._tipEl = document.createElement('div');
      this._tipEl.className = 'tip';
      this._tipEl.setAttribute('role', 'tooltip');
      this._tipEl.hidden = true;
      // Moving the mouse from a block onto its tooltip keeps the tooltip open
      this._tipEl.addEventListener('pointerenter', (event) => {
        if (event.pointerType === 'mouse') {
          this._clearHoverTimer();
          this._hovered = this._activeId();
        }
      });
      this._tipEl.addEventListener('pointerleave', (event) => {
        if (event.pointerType === 'mouse') {
          this._scheduleHoverEnd();
        }
      });
      content.appendChild(this._tipEl);

      card.appendChild(content);
      this.shadowRoot.replaceChildren(style, card);
      this._focused = focusedId && this._blocks.has(focusedId) ? focusedId : null;
      if (this._pinned && !this._blocks.has(this._pinned)) {
        this._pinned = null;
      }
      this._restoreTip();
      if (focusedId && this._blocks.has(focusedId)) {
        this._blocks.get(focusedId).el.focus({ preventScroll: true });
      }
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
      // A stale left offset would shrink the tooltip while measuring it
      tip.style.left = '0px';
      const area = this._content.getBoundingClientRect();
      const anchor = entry.el.getBoundingClientRect();
      const size = tip.getBoundingClientRect();
      const left = anchor.left - area.left + anchor.width / 2 - size.width / 2;
      tip.style.left = `${Math.max(0, Math.min(left, area.width - size.width))}px`;
      const above = anchor.top - area.top - size.height - 6;
      tip.style.top = `${above >= 0 ? above : anchor.bottom - area.top + 6}px`;
    }

    // The most recent interaction wins: mouse hover, then keyboard focus, then a pinned block
    // Sources whose block no longer exists after a re-render are skipped
    _activeId() {
      return [this._hovered, this._focused, this._pinned].find((id) => id && this._blocks.has(id)) ?? null;
    }

    // Shows the tooltip of the active block, or hides it when there is none
    _restoreTip() {
      for (const [id, entry] of this._blocks) {
        entry.el.classList.toggle('selected', id === this._pinned);
      }
      const id = this._activeId();
      if (id) {
        this._showTip(id);
      } else if (this._tipEl) {
        this._tipEl.hidden = true;
      }
    }

    _clearHoverTimer() {
      clearTimeout(this._hoverTimer);
      this._hoverTimer = null;
    }

    // Grace period so the mouse can move from a block onto its tooltip
    _scheduleHoverEnd() {
      this._clearHoverTimer();
      this._hoverTimer = setTimeout(() => {
        this._hoverTimer = null;
        this._hovered = null;
        this._restoreTip();
      }, 150);
    }

    _renderDay(day, intervals, priceVt, priceNt) {
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
      const dateKey = [
        day.date.getFullYear(),
        String(day.date.getMonth() + 1).padStart(2, '0'),
        String(day.date.getDate()).padStart(2, '0'),
      ].join('-');
      this._buildBlocks(intervals, dateKey, priceVt, priceNt).forEach((block) => {
        const id = `${dateKey}-${block.isVt ? 'vt' : 'nt'}-${Math.round(block.start * 60)}-${Math.round(block.end * 60)}`;
        bar.appendChild(this._renderBlock(block, id));
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
        label.textContent = this._formatHour(hour);
        axis.appendChild(label);
      }
      wrapper.appendChild(axis);
      return wrapper;
    }

    _renderBlock(block, id) {
      const label = block.isVt ? this._t('high_tariff_short') : this._t('low_tariff_short');
      const width = ((block.end - block.start) / 24) * 100;
      const text = `${label}: ${this._formatHour(block.start)} - ${this._formatHour(block.end)} (${this._formatPrice(block.price)})`;

      const el = document.createElement('div');
      el.className = 'block';
      el.style.left = `${(block.start / 24) * 100}%`;
      el.style.width = `${width}%`;
      el.style.background = block.isVt ? this._colors.vt : this._colors.nt;
      el.textContent = width > 8 ? label : '';
      el.tabIndex = 0;
      el.dataset.blockId = id;
      el.setAttribute('role', 'button');
      el.setAttribute('aria-label', text);
      this._blocks.set(id, { el, text });

      // Tap/click/Enter pins the tooltip; touch has no hover, so pinning is the only way to see it there
      // Unpinning keeps the tooltip while the block is hovered or focused; a tap also drops the focus so it hides
      const toggle = (blurOnUnpin = false) => {
        const unpin = this._pinned === id;
        this._pinned = unpin ? null : id;
        if (unpin && blurOnUnpin && this._focused === id) {
          this._focused = null;
          el.blur();
        }
        this._restoreTip();
      };
      let pointerType;
      el.addEventListener('pointerdown', (event) => {
        pointerType = event.pointerType;
      });
      el.addEventListener('click', (event) => {
        const clickPointerType = event.pointerType || pointerType;
        pointerType = null;
        toggle(clickPointerType === 'touch');
      });
      el.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          toggle();
        }
      });
      // Mouse hover only: touch pointers also fire pointerenter, which would show a tip that never hides
      el.addEventListener('pointerenter', (event) => {
        if (event.pointerType === 'mouse') {
          this._clearHoverTimer();
          this._hovered = id;
          this._restoreTip();
        }
      });
      el.addEventListener('pointerleave', (event) => {
        if (event.pointerType === 'mouse') {
          this._scheduleHoverEnd();
        }
      });
      el.addEventListener('focus', () => {
        // Keyboard focus is newer than a hover that is still under the mouse
        this._clearHoverTimer();
        this._hovered = null;
        this._focused = id;
        this._restoreTip();
      });
      el.addEventListener('blur', () => {
        if (this._focused === id) {
          this._focused = null;
        }
        this._restoreTip();
      });
      return el;
    }

    // Clips the merged low-tariff intervals from the backend to one day and fills the gaps with high-tariff blocks.
    // Interval times are HA wall-clock times ("YYYY-MM-DDTHH:MM:SS"), compared without the browser time zone.
    _buildBlocks(intervals, dateKey, priceVt, priceNt) {
      const toHours = (value) => {
        const [date, time = '00:00:00'] = String(value).split('T');
        const [year, month, day] = date.split('-').map(Number);
        const [hour, minute, second = 0] = time.split(':').map(Number);
        return Date.UTC(year, month - 1, day, hour, minute, second) / 3600000;
      };
      const dayStart = toHours(dateKey);
      const slots = intervals
        .map((interval) => ({ start: toHours(interval.od) - dayStart, end: toHours(interval.do) - dayStart }))
        .filter((slot) => !isNaN(slot.start) && !isNaN(slot.end) && slot.end > 0 && slot.start < 24)
        .map((slot) => ({ start: Math.max(0, slot.start), end: Math.min(24, slot.end) }));

      const blocks = [];
      let cursor = 0;
      for (const slot of slots) {
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

      legend.appendChild(item(this._colors.vt, `${this._t('high_tariff_short')} (${this._formatPrice(priceVt)})`));
      legend.appendChild(item(this._colors.nt, `${this._t('low_tariff_short')} (${this._formatPrice(priceNt)})`));

      const next = item(null, `${this._t('next_change_in')}: `);
      this._remainingEl = document.createElement('span');
      next.firstChild.appendChild(this._remainingEl);
      legend.appendChild(next);
      return legend;
    }

    // Moves the current-time marker and the countdown without re-rendering
    _tick() {
      if (this._nowMarker) {
        const hour = this._nowHours();
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

    // Current wall-clock time of the HA installation, the same clock the bars use
    _nowHours() {
      const now = new Date();
      const timeZone = this._hass?.config?.time_zone;
      if (timeZone) {
        try {
          const parts = new Intl.DateTimeFormat('en-GB', {
            timeZone, hour: 'numeric', minute: 'numeric', hourCycle: 'h23',
          }).formatToParts(now);
          const value = (type) => Number(parts.find((part) => part.type === type)?.value);
          const hour = value('hour');
          const minute = value('minute');
          if (!isNaN(hour) && !isNaN(minute)) {
            return hour + minute / 60;
          }
        } catch (err) {
          // Unknown time zone: fall back to the browser clock
        }
      }
      return now.getHours() + now.getMinutes() / 60;
    }

    _formatHour(hour) {
      // Keep the midnight boundary for geometry, but display the last minute of this day.
      const minutes = Math.min(LAST_MINUTE_OF_DAY, Math.round(hour * 60));
      const h = Math.floor(minutes / 60);
      const m = minutes % 60;
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
    if (!customElements.get('egd-hdo-card')) {
      customElements.define('egd-hdo-card', HdoChartCard);
    }
    if (!customElements.get('hdo-chart-card')) {
      customElements.define('hdo-chart-card', class LegacyHdoChartCard extends HdoChartCard {});
    }

    window.customCards = window.customCards || [];
    if (!window.customCards.some((card) => card.type === 'egd-hdo-card')) {
      window.customCards.push({
        type: 'egd-hdo-card',
        name: 'HDO Chart Card',
        description: 'Display HDO timeline as horizontal bar chart',
        preview: false,
        documentationURL: 'https://github.com/Antrac1t/HomeAssistant-EGDdistribuce',
      });
    }

    console.info(
      `%c EGD-HDO-CARD %c v${CARD_VERSION}`,
      'color: white; background: #2196f3; font-weight: 700;',
      'color: white; background: #424242; font-weight: 700;'
    );
  });
})();
