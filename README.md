# EGD Distribuce - Home Assistant Sensor

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)

This sensor is downloading json data from EGD webpage. The integration needs the **postal code** and the **HDO code** (A,B,DP). These information can be checked on EGD web site https://www.egd.cz/casy-platnosti-nizkeho-tarifu.
The **postal code** and the **HDO code** have to be defined in configuration.yaml


This sensor shows
- current state of HDO

## Installation

### Step 1: Download files

#### Option 1: Via HACS

Make sure you have HACS installed. If you don't, run `curl -sfSL https://hacs.xyz/install | bash -` in HA.
Then choose Components under HACS. Choose the menu in the upper right, and select Custom repositories. Then add this repo's URL. You should be able to choose to Install now.

#### Option 2: Manual
Clone this repository or download the source code as a zip file and add/merge the `custom_components/` folder with its contents in your configuration directory.

### Step 2: Configure
Add the following to your `configuration.yaml` file:

```yaml
# Example configuration.yaml entry for showing current HDO state
# HDO example (A1B8P05) will be splitted into  A1 -> 1, B8 -> 8, P05 -> 05  
binary_sensor:
  - platform: egddistribuce
    name: HDO
    psc: 
    code_a: "1"
    code_b: "8"
    code_dp: "05"

# HDO example for D57d tarfis you can create multiple binary sensors (A3B7P1,2,6)
binary_sensor:
  - platform: egddistribuce
    name: egdTAR
    psc: 
    code_a: "3"
    code_b: "7"
    code_dp: "01"

  - platform: egddistribuce
    name: egdPV
    psc: 
    code_a: "3"
    code_b: "7"
    code_dp: "02"

  - platform: egddistribuce
    name: egdTUV
    psc: 
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

### Step 3: Restart HA
For the newly added integration to be loaded, HA needs to be restarted.

## References
- PRE Distribuce - Home Assistant Sensor (https://github.com/slesinger/HomeAssistant-PREdistribuce)
- CEZ Distribuce - Home Assistant Sensor (https://github.com/zigul/HomeAssistant-CEZdistribuce)
