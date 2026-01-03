# EGD Distribuce - Home Assistant Sensor

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)

Integrace pro Home Assistant sloužící ke stahování **HDO (Hromadné dálkové ovládání)** dat z API **EG.D Distribuce**.  
Umožňuje sledovat období **nízkého (NT)** a **vysokého tarifu (VT)** elektřiny v České republice.

Integrace podporuje jak **klasické elektroměry**, tak **smart měření**, a je plně konfigurovatelná přes **grafické rozhraní Home Assistantu (GUI)**.

---

## Funkce

- Konfigurace přes GUI (není potřeba YAML)
- Moderní async architektura (DataUpdateCoordinator)
- Automatická aktualizace dat
- Podpora více typů HDO měření
- Podpora klasických i smart elektroměrů
- Detailní atributy pro automatizace a grafy
- Validace zadaných PSČ a HDO kódů
- HDO Timeline - zobrazení jednoduchého grafu

---

## Podporované typy HDO

### 1. Klasické HDO (A + B + DP)
Určeno pro tradiční elektroměry využívající kombinaci kódů **A**, **B** a **DP**.

<img width="351" height="768" alt="{A7547B41-1C31-41BB-AAF3-B42E5CE84658}" src="https://github.com/user-attachments/assets/02075e49-decb-49de-894d-06d555b19c97" />


### 2. HDO Povel 
Pro elektroměry s více HDO příkazy (např. různá relé pro ohřev vody, topení, atd.)

<img width="432" height="682" alt="{5CF42B5D-89D2-48F1-8FF1-3BEDB35B2B35}" src="https://github.com/user-attachments/assets/d6654054-bf97-45d1-8cc3-28505359eb32" />


### 3. Smart Metr
Chytré měřiče s speciálními kódy (Cd56, C55, D56, atd.).

<img width="382" height="596" alt="{605E5EE0-E509-4829-B91F-26D2E357E93A}" src="https://github.com/user-attachments/assets/ff944576-99ec-43f5-b66b-bfe9f197e385" />


## 🎯 Funkce
  - Aktuální cena elektřiny

  - Zbývající čas do změny tarifu

  - Příští HDO časový slot## Installation

-  Automatické Aktualizace - Data se obnovují každé 2 minuty (možnost změnit v nastavení 1-60)

-  Detailní Atributy - Časy dnes/zítra, začátky, konce, region, ceny

-  Validace Dat - Automatické ověření platnosti PSČ a HDO kódů



## Instalace

### Možnost 1: Přes HACS (Doporučeno)
1. Ujistěte se, že máte nainstalovaný [HACS](https://hacs.xyz/)

2. Jděte do HACS → Integrace

3. Klikněte na menu (⋮) vpravo nahoře → Vlastní repozitáře

4. Přidejte tuto URL: `https://github.com/Antrac1t/HomeAssistant-EGDdistribuce`

5. Klikněte Instalovat.

6. Restartujte Home Assistant


### Možnost 2: Manuálně
1. Stáhněte nejnovější release

2. Zkopírujte složku `custom_components/egddistribuce` do vaší složky `config/custom_components/

3. Restartujte Home Assistant



##  Konfigurace

1. Jděte na **Nastavení** → **Zařízení a služby** 

2. Klikněte **+ Přidat integraci**   

3. Vyhledejte "**EGD Distribuce**" 

4. **Vyberte typ konfigurace:**   
<img width="373" height="372" alt="{EFBEC61D-F4EE-42EF-9AB0-5AA49CDD3C9C}" src="https://github.com/user-attachments/assets/8cf13d7e-9dbd-4985-8528-ea8559f9952e" />


##  HDO Timeline nastavení

<img width="485" height="357" alt="{6A53E1BA-5812-42B8-B76E-D1A24A4A118B}" src="https://github.com/user-attachments/assets/466bc63c-16c7-4ffc-97e9-a1a8c306e776" />

1. Jděte na **Nastavení** → **Ovládací panely**
2. Klikněte **...** v pravo nahoře
3. Klikněte na **Zdroje**
4. Přidejte /egddistribuce_card/hdo-chart-card.js
5. Přidejte kartu v Dashboard 

```yaml
type: custom:hdo-chart-card
entity: binary_sensor.NazevSenzoru
title: HDO Timeline
show_days: 2
```




You can show them in a graph, with other entities, for example spot prices from Czech Energy Spot Prices (https://github.com/rnovacek/homeassistant_cz_energy_spot_prices):

![electricity prices graph](docs/graf.png)

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
  - entity: binary_sensor.hdo
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

Since spot prices are (at the moment) hourly and HDO can be in 15 minute increments, for the graph to work well, both entities must have the same interval duration. Function `group_by` takes care of it. In this example it groups by 1 hour, because that works for me well. In your case, maybe `30minutes` or even `15minutes` might be equired.


adding remaining time in GUI page
```yaml
  - entity: binary_sensor.hdo_nizky_tarif
    name: Zbývající čas
    type: attribute
    attribute: remaining_time
```

### Step 3: Restart HA

For the newly added integration to be loaded, HA needs to be restarted.

## References

- PRE Distribuce - Home Assistant Sensor (https://github.com/slesinger/HomeAssistant-PREdistribuce)
- CEZ Distribuce - Home Assistant Sensor (https://github.com/zigul/HomeAssistant-CEZdistribuce)
