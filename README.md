# EGD Distribuce - Home Assistant Integration# EGD Distribuce - Home Assistant Integration



[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)

[![GitHub Release](https://img.shields.io/github/v/release/Antrac1t/HomeAssistant-EGDdistribuce?style=for-the-badge)](https://github.com/Antrac1t/HomeAssistant-EGDdistribuce/releases)

This integration downloads HDO (Hromadné dálkové ovládání) data from EGD Distribuce API. It monitors low/high electricity tariff periods for Czech energy distribution.

Integrace pro stahování HDO (Hromadné dálkové ovládání) dat z API EGD Distribuce. Monitoruje období nízkého a vysokého tarifu elektřiny pro Energetické a průmyslové holdingu (EPH) distribuci v České republice.

## Features

## 🎯 Funkce

- ✨ **GUI Configuration** - Easy setup through Home Assistant UI (no YAML needed!)

- ✨ **GUI Konfigurace** - Snadné nastavení přes Home Assistant UI (bez YAML!)- 🔄 **Async & Modern** - Built with async coordinator for efficient data updates

- 🔄 **Moderní Async** - Postaveno na async coordinatoru pro efektivní aktualizace dat- 📊 **Multiple Sensors**:

- 🎛️ **3 Typy HDO Měření**:  - Binary sensor showing HDO status (on/off)

  - **Klasické HDO** (A+B+DP) - Tradiční elektroměry s kódy A, B, DP  - Current electricity price

  - **HDO Příkazy** (kódy) - Více HDO příkazů najednou (405, 406, 410, atd.)  - Remaining time until tariff change

  - **Smart Metr** - Chytré měřiče s speciálními kódy (Cd56, C55, D56, atd.)  - Next HDO time slot

- 📊 **Kompletní Sensory**:- ⏰ **Automatic Updates** - Data refreshes every 5 minutes

  - Binary sensor: HDO stav (zapnuto/vypnuto)- 📈 **Hourly Prices** - 15-minute interval pricing data for charts

  - Aktuální cena elektřiny- 🎯 **Smart Meter Support** - Works with both traditional and smart meters

  - Zbývající čas do změny tarifu

  - Příští HDO časový slot## Installation

- ⏰ **Automatické Aktualizace** - Data se obnovují každých 15 minut

- 📅 **Detailní Atributy** - Časy dnes/zítra, začátky, konce, region, ceny### Option 1: Via HACS (Recommended)

- 🎯 **Validace Dat** - Automatické ověření platnosti PSČ a HDO kódů

1. Make sure you have [HACS](https://hacs.xyz/) installed

## 📦 Instalace2. Go to HACS → Integrations

3. Click the menu (⋮) in the upper right → Custom repositories

### Možnost 1: Přes HACS (Doporučeno)4. Add this repository URL: `https://github.com/Antrac1t/HomeAssistant-EGDdistribuce`

5. Click Install

1. Ujistěte se, že máte nainstalovaný [HACS](https://hacs.xyz/)6. Restart Home Assistant

2. Jděte do HACS → Integrace

3. Klikněte na menu (⋮) vpravo nahoře → Vlastní repozitáře### Option 2: Manual

4. Přidejte tuto URL: `https://github.com/Antrac1t/HomeAssistant-EGDdistribuce`

5. Klikněte Instalovat1. Download the latest release

6. Restartujte Home Assistant2. Copy the `custom_components/egddistribuce` folder to your `config/custom_components/` directory

3. Restart Home Assistant

### Možnost 2: Manuálně

## Configuration

1. Stáhněte nejnovější release

2. Zkopírujte složku `custom_components/egddistribuce` do vaší složky `config/custom_components/`### GUI Setup (New in v1.0!)

3. Restartujte Home Assistant

1. Go to **Settings** → **Devices & Services**

## ⚙️ Konfigurace2. Click **+ Add Integration**

3. Search for "**EGD Distribuce**"

### GUI Nastavení (Nové v0.6.0!)4. Enter your configuration:

   - **PSČ (Postal Code)**: Your postal code or `smart` for smart meters

1. Jděte na **Nastavení** → **Zařízení a služby**   - **Code A**: Your HDO code A (e.g., `3` or `d57`)

2. Klikněte **+ Přidat integraci**   - **Code B**: (Optional) Your HDO code B (e.g., `7`)

3. Vyhledejte "**EGD Distribuce**"   - **Code DP**: (Optional) Your HDO code DP (e.g., `01`)

4. **Vyberte typ konfigurace:**   - **Price VT**: High tariff price in Kč/kWh

   - **Price NT**: Low tariff price in Kč/kWh

#### 🔹 Typ 1: Klasické HDO (A+B+DP)

You can find your codes on your energy meter or at https://www.egd.cz/casy-platnosti-nizkeho-tarifu

Pro tradiční elektroměry s kódy A, B, DP.

### Finding Your Codes

**Příklad:** Máte kód `A1B8P05` nebo `1B8P5`

**For traditional meters (D57d tariff example):**

```- Code `A3B7P01` splits into: A=`3`, B=`7`, DP=`01`

PSČ: 67168

Kód A: 1**For smart meters:**

Kód B: 8- Use PSČ = `smart`

Kód DP: 05- Code A = `d57` (or your tariff code)

Cena VT: 2.5 Kč/kWh- Leave B and DP empty

Cena NT: 1.5 Kč/kWh

```## Entities



**Kde najít kódy:**After setup, the integration creates these entities:

- Na vašem elektroměru

- V dokumentaci od distributora### Binary Sensor

- Na webu https://www.egd.cz/casy-platnosti-nizkeho-tarifu- **HDO Status** - Shows if HDO is currently active (low tariff period)

  - Attributes: times today/tomorrow, remaining time, current price, region

#### 🔹 Typ 2: HDO Příkazy (kódy)

### Sensors

Pro elektroměry s více HDO příkazy (např. různá relé pro ohřev vody, topení, atd.).- **Aktuální cena** (Current Price) - Current electricity price in Kč/kWh

- **Zbývající čas do změny** (Remaining Time) - Time until next tariff change

**Příklad:** Máte kódy `405`, `406`, `410` pro různá relé (TAR, PV, TUV)- **Další HDO čas** (Next HDO Time) - Next scheduled HDO time slot



```## Usage Examples

PSČ: 37371

HDO kódy: 405,406,410### Simple Lovelace Card

Cena VT: 2.5 Kč/kWh

Cena NT: 1.5 Kč/kWh```yaml

```type: entities

entities:

**Poznámky:**  - entity: binary_sensor.egd_hdo_hdo_status

- Kódy oddělujte čárkou bez mezer: `405,406,410`  - entity: sensor.egd_hdo_aktualni_cena

- Může být i jeden kód: `405`  - entity: sensor.egd_hdo_zbyvajici_cas_do_zmeny

- Integrace automaticky sloučí všechny časy z různých kódů  - entity: sensor.egd_hdo_dalsi_hdo_cas

```

#### 🔹 Typ 3: Smart Metr

### Automation Example

Pro chytré měřiče (TOU - Time Of Use tarify).

Turn on water heater during low tariff:

**Příklad:** Máte smart metr s kódem `Cd56`

```yaml

```automation:

Kód smart metru: Cd56  - alias: "Zapnout ohřev vody při nízkém tarifu"

Cena VT: 2.5 Kč/kWh    trigger:

Cena NT: 1.5 Kč/kWh      - platform: state

```        entity_id: binary_sensor.egd_hdo_hdo_status

        to: "on"

**Typické kódy smart metrů:**    action:

- `Cd56` - Standardní TOU tarif (zimní/letní období)      - service: switch.turn_on

- `C55`, `C56`, `D56` - Další varianty TOU tarifů        entity_id: switch.water_heater



## 📊 Entity  - alias: "Vypnout ohřev vody při vysokém tarifu"

    trigger:

Po nastavení vytvoří integrace tyto entity:      - platform: state

        entity_id: binary_sensor.egd_hdo_hdo_status

### Binary Sensor: `binary_sensor.egd_hdo_hdo_status`        to: "off"

    action:

**Stav:** `on` = HDO aktivní (nízký tarif), `off` = HDO neaktivní (vysoký tarif)      - service: switch.turn_off

        entity_id: switch.water_heater

**Atributy:**```

```yaml

hdo_times_today: "01:45-06, 11:30-13:15, 20:15-22:15"### Price Chart with ApexCharts

hdo_times_tomorrow: "00:45-06:15, 12:45-14:15, 21:15-22:15"

hdo_cas_od: ["01:45:00", "11:30:00", "20:15:00"]Combine with spot prices for comprehensive view:

hdo_cas_do: ["06:00:00", "13:15:00", "22:15:00"]

remaining_time: "2:35"```yaml

current_price: 1.5type: custom:apexcharts-card

region: "VYCHOD"graph_span: 2d

price_vt: 2.5span:

price_nt: 1.5  start: day

hdo_times_today_raw: [{od: "01:45:00", do: "06:00:00"}, ...]header:

hdo_times_tomorrow_raw: [{od: "00:45:00", do: "06:15:00"}, ...]  show: true

```  title: Ceny elektřiny

now:

### Sensors  show: true

  label: Teď

- **`sensor.egd_hdo_aktualni_cena`** - Aktuální cena elektřiny v Kč/kWhseries:

- **`sensor.egd_hdo_zbyvajici_cas`** - Zbývající čas do změny tarifu  - entity: binary_sensor.egd_hdo_hdo_status

- **`sensor.egd_hdo_dalsi_zmena`** - Čas příští změny HDO    name: HDO tarif

    type: column

## 💡 Příklady Použití    data_generator: |

      return entity.attributes.hourly_prices.map((item) => {

### Jednoduchá Lovelace Karta        return [new Date(item[0]).getTime(), item[1]];

      });

```yaml```

type: entities

title: HDO Status## Updating Prices

entities:

  - entity: binary_sensor.egd_hdo_hdo_statusYou can update electricity prices without reconfiguring:

    name: HDO Stav

  - entity: sensor.egd_hdo_aktualni_cena1. Go to **Settings** → **Devices & Services**

    name: Aktuální Cena2. Find your EGD Distribuce integration

  - entity: sensor.egd_hdo_zbyvajici_cas3. Click **Configure**

    name: Zbývá do změny4. Update VT and NT prices

```5. Click Submit



### Automatizace - Zapnutí Ohřevu Vody## Migration from v0.5



```yamlIf you're upgrading from the old YAML configuration:

automation:

  - alias: "Zapnout ohřev při nízkém tarifu"1. **Remove old YAML config** from `configuration.yaml`

    trigger:2. **Restart Home Assistant**

      - platform: state3. **Add integration via GUI** (see Configuration above)

        entity_id: binary_sensor.egd_hdo_hdo_status4. Your entity names will change - update your automations/dashboards accordingly

        to: "on"

    action:Old entities like `binary_sensor.hdo` will become `binary_sensor.egd_hdo_hdo_status`

      - service: switch.turn_on

        target:## Troubleshooting

          entity_id: switch.water_heater

**Integration not showing up:**

  - alias: "Vypnout ohřev při vysokém tarifu"- Make sure you've restarted Home Assistant after installation

    trigger:- Check logs for errors: Settings → System → Logs

      - platform: state

        entity_id: binary_sensor.egd_hdo_hdo_status**Invalid PSČ error:**

        to: "off"- Verify your postal code exists in EGD database

    action:- Try using a nearby postal code

      - service: switch.turn_off- For smart meters, use `smart` instead

        target:

          entity_id: switch.water_heater**No data updating:**

```- Check your internet connection

- Verify EGD API is accessible: https://hdo.distribuce24.cz/region

### Podmíněné Spuštění Spotřebičů- Check integration logs for API errors



Zapnout pračku/myčku jen během HDO (levné elektřiny):## Credits



```yamlOriginal integration by [@Antrac1t](https://github.com/Antrac1t)

automation:

  - alias: "Upozornění - je HDO"## License

    trigger:

      - platform: stateMIT License

        entity_id: binary_sensor.egd_hdo_hdo_status  label: Nyní

        to: "on"header:

    condition:  show: true

      - condition: time  show_states: true

        after: "06:00:00"series:

        before: "22:00:00"  - entity: binary_sensor.hdo

    action:    float_precision: 2

      - service: notify.mobile_app    group_by:

        data:      func: avg

          title: "Levná elektřina!"      duration: 1hour

          message: "Teď je HDO - dobrý čas zapnout pračku nebo myčku."    show:

```      in_header: before_now

    unit: Kč/kWh

### Zobrazení HDO Časů v Karti    data_generator: >

      return  Object.entries(entity.attributes.HDO_HOURLY).map(([date, value],

```yaml      index) => {

type: markdown        return [new Date(date).getTime(), value];

content: |      });

  ## HDO Časy Dnes  - entity: sensor.current_spot_electricity_price

  {{ state_attr('binary_sensor.egd_hdo_hdo_status', 'hdo_times_today') }}    float_precision: 2

      show:

  ## HDO Časy Zítra      in_header: before_now

  {{ state_attr('binary_sensor.egd_hdo_hdo_status', 'hdo_times_tomorrow') }}    data_generator: |

        return Object.entries(entity.attributes).map(([date, value], index) => {

  **Region:** {{ state_attr('binary_sensor.egd_hdo_hdo_status', 'region') }}        return [new Date(date).getTime(), (value + 0.35 + 0.028 + 0.114 )* 1.21];

```      });

```

## 🔧 Změna Cen

Since spot prices are (at the moment) hourly and HDO can be in 15 minute increments, for the graph to work well, both entities must have the same interval duration. Function `group_by` takes care of it. In this example it groups by 1 hour, because that works for me well. In your case, maybe `30minutes` or even `15minutes` might be equired.

Můžete aktualizovat ceny elektřiny bez překonfigurace:



1. Jděte na **Nastavení** → **Zařízení a služby**adding remaining time in GUI page

2. Najděte vaši EGD Distribuce integraci```yaml

3. Klikněte **Konfigurovat**  - entity: binary_sensor.hdo_nizky_tarif

4. Aktualizujte ceny VT a NT    name: Zbývající čas

5. Klikněte Odeslat    type: attribute

    attribute: remaining_time

## 🔄 Migrace z v0.5```



Pokud přecházíte ze staré YAML konfigurace:### Step 3: Restart HA



1. **Odstraňte starou YAML konfiguraci** z `configuration.yaml`:For the newly added integration to be loaded, HA needs to be restarted.

   ```yaml

   # Smažte toto:## References

   binary_sensor:

     - platform: egddistribuce- PRE Distribuce - Home Assistant Sensor (https://github.com/slesinger/HomeAssistant-PREdistribuce)

       psc: "67168"- CEZ Distribuce - Home Assistant Sensor (https://github.com/zigul/HomeAssistant-CEZdistribuce)

       ...
   ```
2. **Restartujte Home Assistant**
3. **Přidejte integraci přes GUI** (viz Konfigurace výše)
4. **Aktualizujte názvy entit** v automatizacích/dashboardech:
   - `binary_sensor.hdo` → `binary_sensor.egd_hdo_hdo_status`
   - `sensor.hdo_current_price` → `sensor.egd_hdo_aktualni_cena`

## 🐛 Řešení Problémů

**Integrace se nezobrazuje:**
- Ujistěte se, že jste restartovali Home Assistant po instalaci
- Zkontrolujte logy: Nastavení → Systém → Logy

**Chyba "Invalid PSČ":**
- Ověřte, že vaše PSČ existuje v databázi EGD
- Zkuste použít PSČ sousedního města
- Pro smart metr NEPOUŽÍVEJTE PSČ, zvolte "Smart metr" v prvním kroku

**Data se neaktualizují:**
- Zkontrolujte internetové připojení
- Ověřte přístupnost API: https://hdo.distribuce24.cz/region
- Zkontrolujte logy integrace

**Žádné HDO časy:**
- Ověřte správnost kódů (A, B, DP nebo HDO kódy)
- Pro typ "HDO Příkazy" zkontrolujte formát: `405,406,410` (bez mezer)
- Pro smart metr ověřte kód (např. `Cd56`, ne `cd56`)

## 📝 Changelog

### v0.6.0 (2026-01-02)
- ✨ Kompletní přepis na moderní async architekturu
- 🎛️ GUI konfigurace s 3 typy HDO měření
- 🔄 Nový DataUpdateCoordinator
- 📊 Rozšířené atributy (hdo_cas_od, hdo_cas_do, remaining_time)
- 🌍 Podpora pro HDO příkazy (více kódů najednou)
- 🎯 Podpora pro smart metry (TOU tarify)
- 🇨🇿 České a anglické překlady

### v0.5.x
- Staré YAML konfigurace
- Základní HDO podpora

## 👏 Kredity

Původní integrace od [@Antrac1t](https://github.com/Antrac1t)

Inspirováno:
- [PRE Distribuce](https://github.com/slesinger/HomeAssistant-PREdistribuce)
- [CEZ Distribuce](https://github.com/zigul/HomeAssistant-CEZdistribuce)

## 📄 Licence

MIT License
