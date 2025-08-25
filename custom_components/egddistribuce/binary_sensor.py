import logging
from . import downloader
import voluptuous as vol
from datetime import datetime, timedelta
from homeassistant.components.binary_sensor import PLATFORM_SCHEMA, BinarySensorEntity
import homeassistant.helpers.config_validation as cv
from homeassistant.util import Throttle
import requests
from typing import Dict

# --- Konstanty pro konfiguraci ---
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
CONF_ID = "id"

# Definice konfiguračního schématu
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_PSC): cv.string,
        vol.Required(CONF_A): cv.string,
        vol.Optional(CONF_B): cv.string,
        vol.Optional(CONF_DP): cv.string,
        vol.Optional(CONF_PRICE_NT): cv.string,
        vol.Optional(CONF_PRICE_VT): cv.string,
        vol.Optional(CONF_ID): cv.string,
    }
)

# --- Vylepšená třída HDOManager s logikou pro zítřek ---
class HDOManager:
    def __init__(self, HDO_Cas_Od, HDO_Cas_Do, HDO_Cas_Od_zitra, HDO_Cas_Do_zitra):
        self.HDO_Cas_Od = HDO_Cas_Od
        self.HDO_Cas_Do = HDO_Cas_Do
        self.HDO_Cas_Od_zitra = HDO_Cas_Od_zitra
        self.HDO_Cas_Do_zitra = HDO_Cas_Do_zitra

    def get_remaining_time(self):
        current_datetime = datetime.now()
        current_time = current_datetime.time()
        
        schedule = []

        # 1. Kontrola dnešních časů
        for start_time_str, end_time_str in zip(self.HDO_Cas_Od, self.HDO_Cas_Do):
            try:
                start_time = datetime.strptime(start_time_str, "%H:%M:%S").time()
                end_time = datetime.strptime(end_time_str, "%H:%M:%S").time()
            except ValueError:
                continue

            if current_time < start_time:
                schedule.append((start_time, end_time))
            elif start_time <= current_time < end_time:
                schedule.append((current_time, end_time))

        if schedule:
            first_start, first_end = schedule[0]
            if current_time < first_start:
                remaining_time = datetime.combine(current_datetime.date(), first_start) - current_datetime
            else:
                remaining_time = datetime.combine(current_datetime.date(), first_end) - current_datetime
            
            remaining_hours = remaining_time.seconds // 3600
            remaining_minutes = (remaining_time.seconds % 3600) // 60
            
            return f"{remaining_hours}:{remaining_minutes}"

        # 2. Pokud se pro dnešek nic nenašlo, kontrolujeme zítřek
        if self.HDO_Cas_Od_zitra:
            first_tomorrow_start_str = self.HDO_Cas_Od_zitra[0]
            first_tomorrow_start_time = datetime.strptime(first_tomorrow_start_str, "%H:%M:%S").time()
            
            tomorrow_start_datetime = datetime.combine(current_datetime.date() + timedelta(days=1), first_tomorrow_start_time)
            
            remaining_time = tomorrow_start_datetime - current_datetime
            
            remaining_hours = remaining_time.days * 24 + remaining_time.seconds // 3600
            remaining_minutes = (remaining_time.seconds % 3600) // 60
            
            return f"{remaining_hours}:{remaining_minutes}"
            
        return "Není dostupný žádný další čas VT/NT"


# --- Home Assistant platform setup ---
def setup_platform(hass, config, add_entities, discovery_info=None):
    name = config.get(CONF_NAME)
    psc = config.get(CONF_PSC)
    codeA = config.get(CONF_A)
    codeB = config.get(CONF_B)
    codeDP = config.get(CONF_DP)
    priceNT = config.get(CONF_PRICE_NT)
    priceVT = config.get(CONF_PRICE_VT)
    entity_id = config.get(CONF_ID)

    add_entities([EgdDistribuce(name, entity_id, psc, codeA, codeB, codeDP, priceNT, priceVT)])

# --- Hlavní třída senzoru pro Home Assistant ---
class EgdDistribuce(BinarySensorEntity):
    def __init__(self, name, entity_id, psc, codeA, codeB, codeDP, priceNT, priceVT):
        self._name = name
        self._unique_id = entity_id
        self.psc = psc
        self.codeA = codeA
        self.codeB = codeB
        self.codeDP = codeDP
        self.priceNT = priceNT if priceNT is not None else 0
        self.priceVT = priceVT if priceVT is not None else 0
        
        self.last_update_success = False
        self.HDO_Cas_Od = []
        self.HDO_Cas_Do = []
        self.HDO_Cas_Od_zitra = []
        self.HDO_Cas_Do_zitra = []
        self.HDO_HOURLY: Dict[datetime, float] = {}
        self.region = "[]"
        self.price = 0
        self.status = False
        self.hdo_manager = None
        self._attributes = {}

    @property
    def unique_id(self):
        return self._unique_id
        
    @property
    def name(self):
        return self._name

    @property
    def icon(self):
        return "mdi:transmission-tower" if self.is_on else "mdi:power-off"

    @property
    def is_on(self):
        """Vrací stav senzoru (True pokud je HDO aktivní, jinak False)."""
        return self.status

    @property
    def extra_state_attributes(self):
        """Vrací další atributy pro senzor."""
        return self._attributes
    
    @property
    def should_poll(self):
        return True

    @property
    def available(self):
        return self.last_update_success

    @Throttle(MIN_TIME_BETWEEN_SCANS)
    def update(self):
        """Aktualizuje data z EGD API a nastavuje stav senzoru."""
        _LOGGER.info("Starting update for EGD HDO sensor.")
        try:
            responseRegion = requests.get(downloader.get_region(), verify=True)
            responseRegion.raise_for_status()
            self.responseRegionJson = responseRegion.json()
            self.region = downloader.parse_region(self.responseRegionJson, self.psc)
            
            responseHDO = requests.get(downloader.get_HDO(), verify=True)
            responseHDO.raise_for_status()
            self.responseHDOJson = responseHDO.json()
            
            (
                self.status, 
                self.HDO_Cas_Od, 
                self.HDO_Cas_Do, 
                self.HDO_HOURLY, 
                self.price, 
                self.HDO_Cas_Od_zitra, 
                self.HDO_Cas_Do_zitra
            ) = downloader.parse_HDO(
                self.responseHDOJson, self.region, self.codeA, self.codeB, self.codeDP, self.priceNT, self.priceVT
            )
            
            self.hdo_manager = HDOManager(self.HDO_Cas_Od, self.HDO_Cas_Do, self.HDO_Cas_Od_zitra, self.HDO_Cas_Do_zitra)
            
            # Naplnění atributů
            self._attributes = {
                'HDO_HOURLY': self.HDO_HOURLY,
                'HDO Times': self.get_times(self.HDO_Cas_Od, self.HDO_Cas_Do),
                'HDO_Times_Tomorrow': self.get_times(self.HDO_Cas_Od_zitra, self.HDO_Cas_Do_zitra),
                'HDO_Cas_Od': self.HDO_Cas_Od,
                'HDO_Cas_Do': self.HDO_Cas_Do,
                'current_price': self.price,
                'remaining_time': self.hdo_manager.get_remaining_time()
            }
            
            self.last_update_success = True
            _LOGGER.info("EGD HDO sensor updated successfully.")
            
        except (requests.exceptions.RequestException, ValueError) as e:
            _LOGGER.error(f"Error updating EGD sensor: {e}")
            self.last_update_success = False

    def get_times(self, od_list, do_list):
        timeReport = []
        for i, start_time in enumerate(od_list):
            timeReport.append(f'{start_time.replace(":00", "")} - {do_list[i].replace(":00", "")}')
        return ', '.join(timeReport)

