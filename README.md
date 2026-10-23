> 🇬🇧 **English description can be found here: [README.en.md](README.en.md)**

# EGD Distribuce - Home Assistant Sensor

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)

Integrace pro Home Assistant sloužící ke stahování **HDO (Hromadné dálkové ovládání)** dat z API **EG.D Distribuce**.  
Umožňuje sledovat období **nízkého (NT)** a **vysokého tarifu (VT)** elektřiny v České republice.

Integrace podporuje jak **klasické elektroměry**, tak **chytré elektroměry**, a je plně konfigurovatelná přes **grafické rozhraní Home Assistantu (GUI)**.

---

## Funkce

- Konfigurace přes GUI (není potřeba YAML)
- Moderní async architektura (DataUpdateCoordinator)
- Automatická aktualizace dat
- Podpora více typů HDO měření
- Podpora klasických i chytrých elektroměrů
- Detailní atributy pro automatizace a grafy
- Validace zadaných PSČ a HDO kódů
- HDO Timeline - zobrazení jednoduchého grafu
- Nastavitelné ceny VT/NT, jednotka ceny a barvy tarifů (i dodatečně v **Nastavení** integrace)

### Entity

| Entita | Název | Popis |
|---|---|---|
| Binární senzor | **HDO stav** | Aktuální stav HDO (nízký tarif NT zapnutý/vypnutý), atributy s časy, cenami, regionem a `HDO_HOURLY` |
| Binární senzor | **Změna HDO časů** | Zapnutý, pokud se zítřejší HDO časy liší od dnešních |
| Binární senzor | **Stav aktualizace API** | Zapnutý, pokud jsou data čerstvě stažená z API (atributy `status`: `online`/`cache`/`offline`, `last_update`) |
| Senzor | **Aktuální cena** | Aktuální cena elektřiny podle tarifu (VT/NT) |
| Senzor | **Další změna HDO** | Časové razítko příští změny tarifu (frontend zobrazí odpočet) |
| Senzor | **Další HDO čas** | Příští HDO časový slot |
| Tlačítko | **Obnovit data z API** | Okamžité stažení dat z API |

---

## Podporované typy HDO

### 1. Klasické HDO (A+B+DP)
Určeno pro tradiční elektroměry využívající kombinaci kódů **A**, **B** a **DP**. Zadáváte PSČ, kód A (1-9), kód B (1-9) a kód DP (01-16).

<img width="360" alt="Klasické HDO (A+B+DP)" src="docs/conf-classic.cs.png" />


### 2. Více HDO příkazů (kódy)
Pro elektroměry s více HDO příkazy (např. různá relé pro ohřev vody, topení, atd.). Zadáváte PSČ a HDO kódy oddělené čárkou (např. `405,406,410`).

<img width="360" alt="Více HDO příkazů (kódy)" src="docs/conf-commands.cs.png" />


### 3. Chytré elektroměry (speciální přístroje)
Chytré elektroměry se speciálními kódy (Cd56, C55, D56, atd.). Zadáváte kód chytrého elektroměru.
Záleží na velikosti písmen a některé elektroměry mohou zobrazovat pomlčku místo podtržítka (na elektroměru je např. `CD2526-3`).
Zadávaný kód musí odpovídat formátu na https://hdo.distribuce24.cz/casy (výsledný kód je `Cd2526_3`).

<img width="412" height="191" alt="image" src="https://github.com/user-attachments/assets/aaa17e89-8873-48ff-856e-0d6f7f3b9bd3" />

<img width="360" alt="Chytré elektroměry" src="docs/conf-smart.cs.png" />

---

## Aktualizace dat

- **Automatická aktualizace** - HDO rozvrh se stahuje z API jednou za hodinu (interval je pevný, v `coordinator.py` konstanta `API_UPDATE_INTERVAL`). Stav HDO se přepíná přesně v okamžiku změny, bez pravidelného dotazování. Při výpadku API se použije cache a za 5 minut se zkusí nové stažení. Data lze stáhnout ihned tlačítkem **Obnovit data z API**.
- **Detailní atributy** - Časy dnes/zítra, začátky, konce, region, ceny.
- **Validace dat** - Automatické ověření platnosti PSČ a HDO kódů.

---

## Instalace

### Možnost 1: Přes HACS (doporučeno)
1. Ujistěte se, že máte nainstalovaný [HACS](https://hacs.xyz/)

2. Jděte do HACS → Integrace

3. Klikněte na menu (⋮) vpravo nahoře → Vlastní repozitáře

4. Přidejte tuto URL: `https://github.com/Antrac1t/HomeAssistant-EGDdistribuce`

5. Klikněte Instalovat.

6. Restartujte Home Assistant


### Možnost 2: Manuálně
1. Stáhněte nejnovější release

2. Zkopírujte složku `custom_components/egddistribuce` do vaší složky `config/custom_components/`

3. Restartujte Home Assistant


## Konfigurace

1. Jděte na **Nastavení** → **Zařízení a služby**

2. Klikněte **+ Přidat integraci**

3. Vyhledejte "**EGD Distribuce**"

4. **Vyberte typ konfigurace:**   
<img width="360" alt="Typ konfigurace" src="docs/conf-types.cs.png" />

5. Zadejte požadované údaje (PSČ, kódy A/B/DP, HDO kódy nebo kód chytrého elektroměru) a volitelně ceny VT/NT, jednotku ceny a barvy tarifů. Ceny, jednotku i barvy lze později změnit v **Nastavení** integrace.


## HDO Timeline nastavení

<img width="485" height="357" alt="{6A53E1BA-5812-42B8-B76E-D1A24A4A118B}" src="https://github.com/user-attachments/assets/466bc63c-16c7-4ffc-97e9-a1a8c306e776" />

1. Jděte na **Nastavení** → **Ovládací panely**
2. Klikněte **...** vpravo nahoře
3. Klikněte na **Zdroje**
4. Přidejte `/egddistribuce_card/hdo-chart-card.js` (typ **JavaScript modul**)
5. Přidejte kartu do dashboardu

```yaml
type: custom:hdo-chart-card
entity: binary_sensor.egd_hdo_hdo_status # senzor HDO Status, přesné ID závisí na názvu zařízení
title: HDO Timeline
show_days: 2
show_header: false
```

Texty karty se překládají podle jazyka Home Assistantu. Překlady jsou v `custom_components/egddistribuce/hdo_card_translations/<jazyk>.json` (zatím `cs` a `en`, ostatní jazyky použijí angličtinu). Nový jazyk stačí přidat jako další soubor.

---

## Příklady

### Graf s dalšími entitami

HDO lze zobrazit v grafu spolu s dalšími entitami, například se spotovými cenami z integrace Czech Energy Spot Prices (https://github.com/rnovacek/homeassistant_cz_energy_spot_prices):

![Graf cen elektřiny](docs/graf.png)

```yaml
type: custom:apexcharts-card
graph_span: 2d
span:
  start: day
stacked: true
apex_config:
  legend:
    show: false
  yaxis:
    tickAmount: 16
    max: 8
all_series_config:
  type: column
now:
  show: true
  label: Nyní
header:
  show: true
  show_states: true
series:
  - entity: binary_sensor.egd_hdo_hdo_status # Podle pojmenování zařízení najděte senzor *_hdo_status
    float_precision: 2
    group_by:
      func: avg
      duration: 1hour
    show:
      in_header: before_now
    unit: Kč/kWh
    data_generator: >
      return  Object.entries(entity.attributes.HDO_HOURLY).map(([date, value],
      index) => {
        return [new Date(date).getTime(), value];
      });
  - entity: sensor.current_spot_electricity_price
    float_precision: 2
    show:
      in_header: before_now
    data_generator: |
      return Object.entries(entity.attributes).map(([date, value], index) => {
        return [new Date(date).getTime(), (value + 0.35 + 0.028 + 0.114 )* 1.21];
      });
```

Spotové ceny jsou (zatím) hodinové, ale HDO může mít 15minutové intervaly. Aby graf fungoval dobře, musí mít obě entity stejnou délku intervalu – o to se stará funkce `group_by`. V tomto příkladu se seskupuje po 1 hodině, což mi dobře vyhovuje. Ve vašem případě může být potřeba `30minutes` nebo i `15minutes`.

### Čas příští změny HDO

Čas příští změny HDO na dashboardu (frontend ho zobrazí jako živý relativní čas, např. „za 23 minut“):
```yaml
  - entity: sensor.hdo_next_hdo_change # timestamp senzor, název závisí na pojmenování zařízení
    name: Další změna
    format: relative
```

Senzor „Zbývající čas do změny“ (`Time Until Change`) a atribut `remaining_time` byly odstraněny (měnily se každou minutu a zaplňovaly logbook). Použijte timestamp senzor **Další změna HDO**. Dá se s ním spouštět i automatizace přesně v okamžiku přepnutí:
```yaml
trigger:
  - trigger: time
    at: sensor.hdo_next_hdo_change
```

---

## Odkazy

- PRE Distribuce - Home Assistant Sensor (https://github.com/slesinger/HomeAssistant-PREdistribuce)
- CEZ Distribuce - Home Assistant Sensor (https://github.com/zigul/HomeAssistant-CEZdistribuce)
