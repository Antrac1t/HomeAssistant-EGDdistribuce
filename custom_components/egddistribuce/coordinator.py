"""Coordinator for EGD Distribuce integration."""
from datetime import datetime, timedelta, time
import logging
from typing import Any, Dict

import aiohttp
import async_timeout
import holidays

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

try:
    from .const import (
        DOMAIN,
        CONFIG_TYPE_CLASSIC,
        CONFIG_TYPE_HDO_CODES,
        CONFIG_TYPE_SMART,
    )
except ImportError:
    # Pro testování mimo HA
    DOMAIN = "egddistribuce"
    CONFIG_TYPE_CLASSIC = "classic"
    CONFIG_TYPE_HDO_CODES = "hdo_codes"
    CONFIG_TYPE_SMART = "smart"

_LOGGER = logging.getLogger(__name__)

API_REGION_URL = "https://hdo.distribuce24.cz/region"
API_HDO_URL = "https://hdo.distribuce24.cz/casy"

UPDATE_INTERVAL = timedelta(minutes=2)


class EGDDistribuceCoordinator(DataUpdateCoordinator):
    """Coordinator for fetching and parsing EGD HDO data."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_type: str,
        psc: str = None,
        code_a: str = None,
        code_b: str = None,
        code_dp: str = None,
        hdo_code: str = None,
        price_nt: float = 1.5,
        price_vt: float = 2.5,
    ):
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.config_type = config_type
        self.psc = psc
        self.code_a = code_a
        self.code_b = code_b
        self.code_dp = code_dp
        self.hdo_code = hdo_code
        self.price_nt = price_nt
        self.price_vt = price_vt
        self.cz_holidays = holidays.country_holidays('CZ')

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from API."""
        try:
            async with async_timeout.timeout(30):
                async with aiohttp.ClientSession() as session:
                    # Krok 1: Stáhnout HDO data
                    hdo_data = await self._fetch_hdo_data(session)
                    
                    # Krok 2: Najít relevantní záznamy podle typu konfigurace
                    if self.config_type == CONFIG_TYPE_CLASSIC:
                        filtered = await self._filter_classic(session, hdo_data)
                    elif self.config_type == CONFIG_TYPE_HDO_CODES:
                        filtered = await self._filter_hdo_codes(session, hdo_data)
                    else:  # CONFIG_TYPE_SMART
                        filtered = self._filter_smart(hdo_data)
                    
                    # Krok 3: Zparsovat časy z filtrovaných záznamů
                    return self._parse_times(filtered)
                    
        except Exception as err:
            raise UpdateFailed(f"Error fetching data: {err}")

    async def _fetch_hdo_data(self, session: aiohttp.ClientSession) -> list:
        """Stáhnout HDO data z API."""
        async with session.get(API_HDO_URL) as response:
            response.raise_for_status()
            return await response.json()

    async def _fetch_region(self, session: aiohttp.ClientSession) -> str:
        """Zjistit region z PSČ."""
        async with session.get(API_REGION_URL) as response:
            response.raise_for_status()
            data = await response.json()
            
        region_records = [x for x in data if x.get('PSC') == self.psc]
        if not region_records:
            raise UpdateFailed(f"Region not found for PSČ: {self.psc}")
        
        # Vrátit první unikátní region
        return region_records[0]['Region']

    async def _filter_classic(self, session: aiohttp.ClientSession, hdo_data: list) -> list:
        """VARIANTA 1: Classic - PSČ + A + B + DP"""
        region = await self._fetch_region(session)
        
        _LOGGER.debug(f"Classic filter: region={region}, A={self.code_a}, B={self.code_b}, DP={self.code_dp}")
        
        filtered = [
            x for x in hdo_data
            if x.get('region') == region
            and x.get('A') == self.code_a
            and x.get('B') == self.code_b
            and (x.get('DP') == self.code_dp or x.get('DP') == '0' + self.code_dp)
        ]
        
        _LOGGER.debug(f"Classic filter: found {len(filtered)} records")
        return filtered

    async def _filter_hdo_codes(self, session: aiohttp.ClientSession, hdo_data: list) -> list:
        """VARIANTA 2: HDO Codes - PSČ + seznam kódů (405,406,410)"""
        region = await self._fetch_region(session)
        codes = [c.strip() for c in self.hdo_code.split(',')]
        
        _LOGGER.debug(f"HDO Codes filter: region={region}, codes={codes}")
        
        filtered = []
        for code in codes:
            matches = [
                x for x in hdo_data
                if x.get('region') == region
                and x.get('kodHdo_A') == code
            ]
            filtered.extend(matches)
        
        _LOGGER.debug(f"HDO Codes filter: found {len(filtered)} records")
        return filtered

    def _filter_smart(self, hdo_data: list) -> list:
        """VARIANTA 3: Smart - jen kodHdo_A (Cd56), žádný region"""
        _LOGGER.debug(f"Smart filter: code={self.hdo_code}")
        
        filtered = [
            x for x in hdo_data
            if x.get('kodHdo_A') == self.hdo_code
        ]
        
        _LOGGER.debug(f"Smart filter: found {len(filtered)} records")
        return filtered

    def _parse_times(self, filtered_records: list) -> Dict[str, Any]:
        """Zparsovat HDO časy z filtrovaných záznamů."""
        date_now = datetime.now().date()
        date_tomorrow = date_now + timedelta(days=1)
        current_month = datetime.now().month
        
        hdo_times_today = []
        hdo_times_tomorrow = []
        
        _LOGGER.debug(f"Parsing {len(filtered_records)} records for date={date_now}")
        
        for record in filtered_records:
            od_year = int(record['od']['rok'])
            od_month = int(record['od']['mesic'])
            do_month = int(record['do']['mesic'])
            
            # Kontrola platnosti záznamu
            if od_year == 9999:
                # Pattern který se opakuje každý rok (např. léto/zima)
                if od_month <= do_month:
                    # Normální období (např. 4-9)
                    if not (od_month <= current_month <= do_month):
                        continue
                else:
                    # Období přes rok (např. 10-3)
                    if not (current_month >= od_month or current_month <= do_month):
                        continue
            else:
                # Konkrétní rok - validace přes datum
                current_year = datetime.now().year
                do_year = int(record['do']['rok'])
                
                if od_year < current_year and od_month > current_month:
                    current_year = current_year - 1
                if do_year < od_year:
                    do_year = do_year + 1
                
                try:
                    date_od = datetime(current_year, od_month, int(record['od']['den'])).date()
                    date_do = datetime(do_year, do_month, int(record['do']['den'])).date()
                except ValueError:
                    continue
                
                if not (date_od <= date_now <= date_do):
                    continue
            
            # Záznam je platný - zparsovat časy
            for sazba in record.get('sazby', []):
                for day in sazba.get('dny', []):
                    day_code = day['denVTydnu']
                    
                    # Dnes
                    if self._is_matching_day(date_now, day_code):
                        for cas in day.get('casy', []):
                            hdo_times_today.append({'od': cas['od'], 'do': cas['do']})
                    
                    # Zítra
                    if self._is_matching_day(date_tomorrow, day_code):
                        for cas in day.get('casy', []):
                            hdo_times_tomorrow.append({'od': cas['od'], 'do': cas['do']})
        
        # Seřadit časy
        hdo_times_today = sorted(hdo_times_today, key=lambda x: x['od'])
        hdo_times_tomorrow = sorted(hdo_times_tomorrow, key=lambda x: x['od'])
        
        _LOGGER.debug(f"Found {len(hdo_times_today)} slots today, {len(hdo_times_tomorrow)} tomorrow")
        
        # Získat region z prvního záznamu (pokud existuje)
        region = filtered_records[0].get('region', 'N/A') if filtered_records else 'N/A'
        
        # Pro TOU (Time of Use) tariffy jsou časy INVERTOVANÉ
        # API časy znamenají kdy JE nízký tarif (NT), ne HDO signál
        is_tou = region == 'TOU'
        
        # Zjistit aktuální stav a zbývající čas
        current_time = datetime.now().time()
        is_active = self._is_time_active(current_time, hdo_times_today)
        
        # Pro TOU invertovat stav (časy = kdy JE NT, ne kdy je HDO signál)
        if is_tou:
            is_active = not is_active
        
        remaining_time = self._calculate_remaining_time(current_time, hdo_times_today, hdo_times_tomorrow, is_tou)
        
        # Vygenerovat HDO_HOURLY pro dalších 24 hodin
        HDO_HOURLY = self._generate_hdo_hourly(hdo_times_today, hdo_times_tomorrow, is_tou)
        
        return {
            "is_active": is_active,
            "hdo_times_today": hdo_times_today,
            "hdo_times_tomorrow": hdo_times_tomorrow,
            "current_price": self.price_nt if is_active else self.price_vt,
            "remaining_time": remaining_time,
            "region": region,
            "HDO_HOURLY": HDO_HOURLY,
        }

    def _is_matching_day(self, date: datetime.date, day_code: int) -> bool:
        """Kontrola zda datum odpovídá kódu dne."""
        is_holiday = date in self.cz_holidays
        
        # Svátek = neděle
        if is_holiday and day_code == 7:
            return True
        
        # Pracovní den
        if not is_holiday and date.isoweekday() == day_code:
            return True
        
        return False

    def _is_time_active(self, current_time: time, hdo_times: list) -> bool:
        """Kontrola zda je aktuální čas v HDO slotu."""
        for slot in hdo_times:
            try:
                start = datetime.strptime(slot['od'], "%H:%M:%S").time()
                end = datetime.strptime(slot['do'], "%H:%M:%S").time()
                
                # Speciální případ: 23:59:00 znamená konec dne (23:59:59)
                if slot['do'] == '23:59:00':
                    # Kontrola: start <= current_time <= 23:59:59
                    end_of_day = time(23, 59, 59)
                    if start <= current_time <= end_of_day:
                        return True
                else:
                    # Fix pro ostatní časy končící :59:00 (měly by být :00:00 další hodiny)
                    if slot['do'].endswith(':59:00'):
                        end = (datetime.combine(datetime.today(), end) + timedelta(minutes=1)).time()
                    
                    if start <= current_time < end:
                        return True
            except ValueError:
                continue
        
        return False

    def _calculate_remaining_time(self, current_time: time, hdo_times_today: list, hdo_times_tomorrow: list, is_tou: bool = False) -> str:
        """Vypočítat zbývající čas do změny HDO.
        
        Args:
            is_tou: Pokud True, časy jsou invertované (značí kdy JE NT, ne HDO signál)
        """
        now = datetime.now()
        
        # Pro TOU zjistit jestli jsme MIMO slot (= jsme v NT)
        is_in_slot = self._is_time_active(current_time, hdo_times_today)
        
        if is_tou:
            # Pro TOU: pokud jsme VE slotu, jsme v NT, zbývá do konce NT
            # Pokud jsme MIMO slot, jsme ve VT, zbývá do začátku NT
            if is_in_slot:
                # Jsme v NT - najít konec slotu
                for slot in hdo_times_today:
                    try:
                        start = datetime.strptime(slot['od'], "%H:%M:%S").time()
                        end = datetime.strptime(slot['do'], "%H:%M:%S").time()
                        
                        if slot['do'].endswith(':59:00'):
                            end = (datetime.combine(datetime.today(), end) + timedelta(minutes=1)).time()
                        
                        if start <= current_time < end:
                            end_datetime = datetime.combine(now.date(), end)
                            remaining = end_datetime - now
                            hours, remainder = divmod(remaining.seconds, 3600)
                            minutes = remainder // 60
                            return f"{hours}:{minutes:02d}"
                    except ValueError:
                        continue
            else:
                # Jsme ve VT - najít začátek dalšího NT slotu
                for slot in hdo_times_today:
                    try:
                        start = datetime.strptime(slot['od'], "%H:%M:%S").time()
                        if start > current_time:
                            start_datetime = datetime.combine(now.date(), start)
                            remaining = start_datetime - now
                            hours, remainder = divmod(remaining.seconds, 3600)
                            minutes = remainder // 60
                            return f"{hours}:{minutes:02d}"
                    except ValueError:
                        continue
        else:
            # Klasické HDO - pokud je aktivní, najít konec
            if is_in_slot:
                for slot in hdo_times_today:
                    try:
                        start = datetime.strptime(slot['od'], "%H:%M:%S").time()
                        end = datetime.strptime(slot['do'], "%H:%M:%S").time()
                        
                        if slot['do'].endswith(':59:00'):
                            end = (datetime.combine(datetime.today(), end) + timedelta(minutes=1)).time()
                        
                        if start <= current_time < end:
                            end_datetime = datetime.combine(now.date(), end)
                            remaining = end_datetime - now
                            hours, remainder = divmod(remaining.seconds, 3600)
                            minutes = remainder // 60
                            return f"{hours}:{minutes:02d}"
                    except ValueError:
                        continue
            else:
                # HDO není aktivní - najít začátek dalšího slotu
                for slot in hdo_times_today:
                    try:
                        start = datetime.strptime(slot['od'], "%H:%M:%S").time()
                        if start > current_time:
                            start_datetime = datetime.combine(now.date(), start)
                            remaining = start_datetime - now
                            hours, remainder = divmod(remaining.seconds, 3600)
                            minutes = remainder // 60
                            return f"{hours}:{minutes:02d}"
                    except ValueError:
                        continue
        
        # Žádný další slot dnes - vrátit čas do prvního slotu zítra
        if hdo_times_tomorrow:
            try:
                first_tomorrow = datetime.strptime(hdo_times_tomorrow[0]['od'], "%H:%M:%S").time()
                tomorrow = now.date() + timedelta(days=1)
                next_datetime = datetime.combine(tomorrow, first_tomorrow)
                remaining = next_datetime - now
                hours, remainder = divmod(remaining.seconds, 3600)
                minutes = remainder // 60
                return f"{hours}:{minutes:02d}"
            except ValueError:
                pass
        
        return "N/A"

    def _generate_hdo_hourly(self, hdo_times_today: list, hdo_times_tomorrow: list, is_tou: bool = False) -> dict:
        """Vygenerovat HDO_HOURLY atribut - 15minutové intervaly na 48 hodin (dnes + zítra).
        
        Args:
            is_tou: Pokud True, časy jsou invertované (značí kdy JE NT, ne HDO signál)
        """
        now = datetime.now()
        result = {}
        date_today = now.date()
        date_tomorrow = date_today + timedelta(days=1)
        
        # Generovat dnes (96 intervalů = 24 hodin * 4)
        for i in range(96):
            timestamp = datetime.combine(date_today, time(hour=0)) + timedelta(minutes=i * 15)
            time_check = timestamp.time()
            
            is_in_slot = self._is_time_active(time_check, hdo_times_today)
            
            # Pro TOU: ve slotu = NT, mimo slot = VT
            # Pro klasické HDO: ve slotu = NT (HDO aktivní)
            if is_tou:
                price = self.price_nt if is_in_slot else self.price_vt
            else:
                price = self.price_nt if is_in_slot else self.price_vt
            
            # Použít datetime objekt jako klíč (bez timezone) - kompatibilní se starou verzí
            result[timestamp] = float(price)
        
        # Generovat zítra (96 intervalů = 24 hodin * 4)
        for i in range(96):
            timestamp = datetime.combine(date_tomorrow, time(hour=0)) + timedelta(minutes=i * 15)
            time_check = timestamp.time()
            
            is_in_slot = self._is_time_active(time_check, hdo_times_tomorrow)
            
            # Pro TOU: ve slotu = NT, mimo slot = VT
            # Pro klasické HDO: ve slotu = NT (HDO aktivní)
            if is_tou:
                price = self.price_nt if is_in_slot else self.price_vt
            else:
                price = self.price_nt if is_in_slot else self.price_vt
            
            # Použít datetime objekt jako klíč (bez timezone) - kompatibilní se starou verzí
            result[timestamp] = float(price)
        
        return result
