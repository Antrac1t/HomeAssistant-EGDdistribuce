__version__ = "0.3"

import logging
from . import downloader
import voluptuous as vol
from datetime import datetime, timedelta
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

class HDOManager:
    def __init__(self, HDO_Cas_Od, HDO_Cas_Do):
        self.HDO_Cas_Od = HDO_Cas_Od
        self.HDO_Cas_Do = HDO_Cas_Do

    def get_remaining_time(self):
        current_time = datetime.now().time()  # Pouze čas
        schedule = []
        print(current_time)
        for start_time_str, end_time_str in zip(self.HDO_Cas_Od, self.HDO_Cas_Do):
            try:
                start_time = datetime.strptime(start_time_str, "%H:%M:%S").time()
                end_time = datetime.strptime(end_time_str, "%H:%M:%S").time()
            except ValueError as e:
                continue

            if current_time < start_time:
                schedule.append((start_time, end_time))
            elif start_time <= current_time < end_time:
                schedule.append((current_time, end_time))

        if not schedule:
            return "Není dostupný žádný další čas VT/NT"

        first_start, first_end = schedule[0]

        if current_time < first_start:
            remaining_time = datetime.combine(datetime.today(), first_start) - datetime.combine(datetime.today(), current_time)
        else:
            remaining_time = datetime.combine(datetime.today(), first_end) - datetime.combine(datetime.today(), current_time)

        remaining_hours = remaining_time.seconds // 3600
        remaining_minutes = (remaining_time.seconds % 3600) // 60

        return f"{remaining_hours}h {remaining_minutes}m"



def setup_platform(hass, config, add_entities, discovery_info=None):
    name = config.get(CONF_NAME)
    psc = config.get(CONF_PSC)
    codeA = config.get(CONF_A)
    codeB = config.get(CONF_B)
    codeDP = config.get(CONF_DP)
    priceNT = config.get(CONF_PRICE_NT)
    priceVT = config.get(CONF_PRICE_VT)

    add_entities([EgdDistribuce(name, psc, codeA, codeB, codeDP, priceNT, priceVT)])


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
        self.hdo_manager = HDOManager(self.HDO_Cas_Od, self.HDO_Cas_Do)

        self.priceNT = priceNT if priceNT is not None else 0
        self.priceVT = priceVT if priceVT is not None else 0

    @property
    def name(self):
        return self._name

    @property
    def icon(self):
        return "mdi:transmission-tower" if self.status else "mdi:power-off"

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
            'current_price': self.price,
            'remaining_time': self.hdo_manager.get_remaining_time()
        }

    @property
    def should_poll(self):
        return True

    @property
    def available(self):
        return self.last_update_success

    @property
    def device_class(self):
        return 'monetary'

    @property
    def unit_of_measurement(self):
        return 'Kč/kWh'

    def get_times(self):
        timeReport = []
        for i, start_time in enumerate(self.HDO_Cas_Od):
            timeReport.append(f'{start_time.replace(":00", "")} - {self.HDO_Cas_Do[i].replace(":00", "")}')
        return ', '.join(timeReport)

    @Throttle(MIN_TIME_BETWEEN_SCANS)
    def update(self):
        responseRegion = requests.get(downloader.get_region(), verify=True)
        if responseRegion.status_code == 200:
            self.responseRegionJson = responseRegion.json()
            self.region = downloader.parse_region(self.responseRegionJson, self.psc)
            responseHDO = requests.get(downloader.get_HDO(), verify=True)
            if responseHDO.status_code == 200:
                self.responseHDOJson = responseHDO.json()
                self.hdo_manager = HDOManager(self.HDO_Cas_Od, self.HDO_Cas_Do)
                self.last_update_success = True
        else:
            self.last_update_success = False
