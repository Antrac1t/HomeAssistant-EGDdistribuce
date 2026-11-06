// Run with: node --test tests\test_hdo_chart_card.cjs
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const { runInNewContext } = require('node:vm');

class Element {
  constructor() {
    this.children = [];
    this.style = {};
    this.dataset = {};
    this.attributes = {};
    this.classList = { add() {} };
  }

  attachShadow() {}
  appendChild(child) { this.children.push(child); }
  append(...children) { this.children.push(...children); }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener() {}
}

const elements = new Map();
runInNewContext(
  readFileSync(join(__dirname, '..', 'custom_components', 'egddistribuce', 'hdo_chart_card.js'), 'utf8'),
  {
    HTMLElement: Element,
    document: { createElement: () => new Element() },
    customElements: {
      whenDefined: () => ({ then: (callback) => callback() }),
      get: (name) => elements.get(name),
      define: (name, element) => elements.set(name, element),
    },
    window: {},
    console: { info() {} },
  },
);
const HdoChartCard = elements.get('egd-hdo-card');

function createCard() {
  const card = new HdoChartCard();
  card._colors = { vt: 'red', nt: 'blue' };
  card._formatPrice = (price) => String(price);
  return card;
}

test('clock labels stay within the day and normalize rounded minutes', () => {
  const card = createCard();
  for (const [hour, expected] of [
    [0, '0:00'], [6, '6:00'], [12, '12:00'], [18, '18:00'],
    [12.5, '12:30'], [23 + 59 / 60, '23:59'], [24, '23:59'],
    [23 + 59.9 / 60, '23:59'], [5 + 59.9 / 60, '6:00'],
  ]) {
    assert.equal(card._formatHour(hour), expected);
  }
});

test('today and tomorrow axes end at 23:59', () => {
  const card = createCard();
  for (const isToday of [true, false]) {
    const day = card._renderDay(
      { key: isToday ? 'today' : 'tomorrow', date: new Date(2026, 10, isToday ? 6 : 7), isToday },
      [], 2, 1,
    );
    const axis = day.children[2];
    assert.deepEqual(axis.children.map((label) => label.textContent), ['0:00', '6:00', '12:00', '18:00', '23:59']);
  }
});

test('high and low tariff blocks keep full-day geometry and consistent end labels', () => {
  const card = createCard();
  const dateKey = '2026-11-06';
  for (const intervals of [
    [],
    [{ od: '2026-11-05T22:00:00', do: '2026-11-07T04:00:00' }],
  ]) {
    const blocks = card._buildBlocks(intervals, dateKey, 2, 1);
    assert.equal(blocks.length, 1);
    assert.equal(blocks[0].start, 0);
    assert.equal(blocks[0].end, 24);
    const el = card._renderBlock(blocks[0], 'full-day');
    assert.equal(el.style.left, '0%');
    assert.equal(el.style.width, '100%');
    assert.match(el.attributes['aria-label'], /0:00 - 23:59/);
    assert.equal(card._blocks.get('full-day').text, el.attributes['aria-label']);
    card._tipEl = new Element();
    card._tipEl.getBoundingClientRect = () => ({ width: 100, height: 20 });
    card._content = { getBoundingClientRect: () => ({ left: 0, top: 0, width: 300 }) };
    el.getBoundingClientRect = () => ({ left: 0, top: 50, bottom: 90, width: 300 });
    card._showTip('full-day');
    assert.equal(card._tipEl.textContent, el.attributes['aria-label']);
  }
});

test('countdown remains a duration and may exceed 23:59', () => {
  const card = createCard();
  const result = card._formatRemaining(new Date(Date.now() + 25 * 3600000 + 30000));
  assert.equal(result, '25:00');
});
