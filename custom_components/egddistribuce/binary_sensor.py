__version__ = "0.4"

import logging
from . import downloader
import voluptuous as vol
from datetime import timedelta
from homeassistant.components.sensor import PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.util import Throttle
import requests


MIN_TIME_BETWEEN_SCANS = timedelta(seconds=300)
_LOGGER = logging.getLogger(__name__)

DOMAIN = "egddistribuce"
CONF_PSC = "psc"
CONF_A = "code_a"
CONF_B = "code_b"
CONF_DP = "code_dp"
CONF_NAME = "name"
CONF_PRICE_NT = 'price_nt'
CONF_PRICE_VT = 'price_vt'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_PSC): cv.string,
        vol.Required(CONF_A): cv.string,
        vol.Optional(CONF_B): cv.string,
        vol.Optional(CONF_DP): cv.string,
        vol.Optional(CONF_PRICE_NT): cv.string,
        vol.Optional(CONF_PRICE_VT): cv.string
    }
)


def setup_platform(hass, config, add_entities, discovery_info=None):
    name = config.get(CONF_NAME)
    psc = config.get(CONF_PSC)
    codeA = config.get(CONF_A)
    codeB = config.get(CONF_B)
    codeDP = config.get(CONF_DP)
    priceNT = config.get(CONF_PRICE_NT)
    priceVT = config.get(CONF_PRICE_VT)

    add_entities(
        [EgdDistribuce(name, psc, codeA, codeB, codeDP, priceNT, priceVT)])


class EgdDistribuce(BinarySensorEntity):
    def __init__(self, name, psc, codeA, codeB, codeDP, priceNT, priceVT):
        """Initialize the sensor."""
        self._name = name
        self.psc = psc
        self.codeA = codeA
        self.codeB = codeB
        self.codeDP = codeDP
        self.responseRegionJson = "[]"
        self.responseHDOJson = "[]"
        self.region = "[]"
        self.status = False
        self.HDO_Cas_Od = []
        self.HDO_Cas_Do = []
        self.update()
        self._attributes = {}

        if priceNT is not None:
            self.priceNT = priceNT
        else:
            self.priceNT = 0

        if priceVT is not None:
            self.priceVT = priceVT
        else:
            self.priceVT = 0

    @property
    def name(self):
        return self._name

    @property
    def icon(self):
        if self.status == True:
            return "mdi:transmission-tower"
        else:
            return "mdi:power-off"

    @property
    def is_on(self):
        self.status, self.HDO_Cas_Od, self.HDO_Cas_Do, self.HDO_HOURLY, self.price = downloader.parse_HDO(
            self, self.responseHDOJson, self.region, self.codeA, self.codeB, self.codeDP, self.priceNT, self.priceVT)

        return self.status

    @property
    def extra_state_attributes(self):
        return {
            'HDO_HOURLY': self.HDO_HOURLY,
            'HDO Times': self.get_times(),
            'HDO_Cas_Od': self.HDO_Cas_Od,
            'HDO_Cas_Do': self.HDO_Cas_Do,
            'current_price': self.price
        }

    @property
    def should_poll(self):
        return True

    @property
    def available(self):
        return self.last_update_success

    @property
    def device_class(self):
        return ''

    def get_times(self):
        i = 0
        timeReport = []
        for n in self.HDO_Cas_Od:
            timeReport.append(
                '{}'.format(n).replace(':00', '') + ' - ' + self.HDO_Cas_Do[i].replace(':00', ''))
            i += 1
        return ', '.join(timeReport)

    @Throttle(MIN_TIME_BETWEEN_SCANS)
    def update(self):
        responseRegion = requests.get(downloader.get_region(), verify=True)
        if responseRegion.status_code == 200:
            self.responseRegionJson = responseRegion.json()
            self.region = downloader.parse_region(
                self.responseRegionJson, self.psc)
            responseHDO = requests.get(downloader.get_HDO(), verify=True)
            if responseHDO.status_code == 200:
                self.responseHDOJson = responseHDO.json()
                self.last_update_success = True
        else:
            self.last_update_success = False
