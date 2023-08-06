__version__ = "0.1"

import logging
from . import downloader
import voluptuous as vol
from datetime import timedelta, datetime, date
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
        self.region ="[]"
        self.status= False
        self.HDO_Cas_Od = []
        self.HDO_Cas_Do = []
        self.update()


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
        self.status, self.HDO_Cas_Od,self.HDO_Cas_Do  = downloader.parseHDO(self.responseHDOJson,self.region,self.codeA,self.codeB,self.codeDP)
        #self.status = downloader.parseHDO(self.responseHDOJson,self.region,self.codeA,self.codeB,self.codeDP)
        return self.status

    @property
    def device_state_attributes(self):
        attributes = {}
        #attributes['response_json'] = downloader.parseHDO(self.responseHDOJson,self.region,self.codeA,self.codeB,self.codeDP)
        attributes['HDO Times'] = self.get_times()
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

    def get_times(self):
        i=0
        timeReport=""
        for n in self.HDO_Cas_Od:
            timeReport = timeReport + '{}'.format(n) + ' - ' +self.HDO_Cas_Do[i] + '\n | '
            i += 1
        return timeReport

    @Throttle(MIN_TIME_BETWEEN_SCANS)
    def update(self):
        responseRegion = requests.get(downloader.getRegion(), verify=False)
        if responseRegion.status_code == 200:
            if len(self.psc) == 2:
                self.region = self.psc
            else:    
                self.responseRegionJson = responseRegion.json() 
                self.region=downloader.parseRegion(self.responseRegionJson,self.psc)
            responseHDO = requests.get(downloader.getHDO(), verify=False)
            if responseHDO.status_code == 200:
                self.responseHDOJson = responseHDO.json()
                self.last_update_success = True
        else:
            self.last_update_success = False
        
