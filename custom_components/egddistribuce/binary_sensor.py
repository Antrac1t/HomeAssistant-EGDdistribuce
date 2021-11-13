__version__ = "0.1"

import logging
import json
from urllib.request import urlopen
from . import downloader
import voluptuous as vol
import datetime
from homeassistant.components.sensor import PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.util import Throttle

import requests
from lxml import html, etree

MIN_TIME_BETWEEN_SCANS = timedelta(seconds=300)
_LOGGER = logging.getLogger(__name__)

DOMAIN = "egddistribuce"
CONF_PSC = "psc"
CONF_A = "code_a"
CONF_B = "code_b"
CONF_DP = "code_dp"
CONF_NAME = "name"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_PSC): cv.string,
        vol.Required(CONF_A): cv.string,
        vol.Required(CONF_B): cv.string, 
        vol.Required(CONF_DP): cv.string,
        vol.Required(CONF_NAME): cv.string,
    }
)

def setup_platform(hass, config, add_entities, discovery_info=None):
    name = config.get(CONF_NAME)
    psc = config.get(CONF_PSC)
    codeA = config.get(CONF_A)
    codeB = config.get(CONF_B)
    codeDP = config.get(CONF_DP)

    ents = []
    ents.append(EgdDistribuce(name,psc,codeA,codeB,codeDP))
    add_entities(ents)

class EgdDistribuce(BinarySensorEntity):
    def __init__(self, name, psc, codeA, codeB, codeDP):
        """Initialize the sensor."""
        self._name = name
        self.psc = psc
        self.codeA = codeA
        self.codeB = codeB
        self.codeDP = codeDP
        self.responseRegionJson = "[]"
        self.responseHDOJson ="[]"
        self.Region = ""
        self.update()

    @property
    def name(self):
        return self._name

    @property
    def icon(self):
        return "mdi:power"

    @property
    def is_on(self):
        return downloader.isHdo(self.codeA,self.codeB,self.codeDP)

    @property
    def device_state_attributes(self):
        attributes = {}
        attributes['response_json'] = self.responseHDOJson
        return attributes

    @property
    def should_poll(self):
        return True

    @property
    def available(self):
        return self.last_update_success

    @property
    def device_class(self):
        return ''

    @Throttle(MIN_TIME_BETWEEN_SCANS)
    def update(self):
        # PSC = "67168"
        # CODE_A = "1"
        # CODE_B = "8"
        # CODE_DP = "05"

        responseRegion = requests.get(downloader.getRegion())
        if responseRegion.status_code == 200:
            self.responseRegionJson = responseRegion.json()
            self.Region=parseRegion(self.responseRegionJson,self.psc)
            responseHDO = requests.get(downloader.getHDO())
            if responseHDO.status_code == 200:
                self.last_update_success = True
                self.responseHDOJson = responseHDO.json()
            #regionHDO=parseHDO(responseHDOJson,regionResult,"1","8","05")

        else:
            self.last_update_success = False

