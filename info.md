#EGD Distribuce

This integration provides sensors informing about low/high energy tariff (HDO), specifically for Czech EGD Distribuce. Technically it downloads data from https://www.egd.cz/casy-platnosti-nizkeho-tarifu.

This sensor shows only the current state of HDO as a binary sensor.

### Example configuration

Add the following to your `configuration.yaml` file:

```yaml
# HDO example for D57d tarif - you can create multiple binary sensors (A3B7P1 A3B7P2 A3B7P6)
# Split `A3B7P01` into  A3 -> 3, B7 -> 7, P01 -> 01
binary_sensor:
  - platform: egddistribuce
    name: egdTAR
    psc: 60200
    code_a: "3"
    code_b: "7"
    code_dp: "01"

  - platform: egddistribuce
    name: egdPV
    psc: 60200
    code_a: "3"
    code_b: "7"
    code_dp: "02"

  - platform: egddistribuce
    name: egdTUV
    psc: 60200
    code_a: "3"
    code_b: "7"
    code_dp: "06"

# HDO example for smart meter with code `d57`
binary_sensor:
  - platform: egddistribuce
    name: egdTAR
    psc: "smart"
    code_a: "d57"
```

You can also specify prices of VT/NT according to your tariff, per 1 kWh to get current distribution price. No VAT calculation is performed, you get one of the prices depending on HDO state.

```yaml
price_vt: "2.11469"
price_nt: "0.24611"
```

Home Assistant needs to be restarted after modifying the configuration.
