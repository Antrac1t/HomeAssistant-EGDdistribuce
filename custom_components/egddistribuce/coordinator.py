"""Coordinator for EGD Distribuce integration."""
from datetime import datetime, timedelta, time
import logging
from typing import Any, Callable, Dict

import aiohttp
import async_timeout
import holidays

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later, async_track_point_in_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from .download import Download

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

# How often the HDO schedule is downloaded from the API
API_UPDATE_INTERVAL = timedelta(hours=1)
# Retry delay when the API failed and cached data is being used
RETRY_DELAY = timedelta(minutes=5)
# Margin after an interval boundary so that start <= now < end already holds
BOUNDARY_MARGIN = timedelta(seconds=1)


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
        color_vt: str = "#ff5252",  # Red for high tariff
        color_nt: str = "#2196f3",  # Blue for low tariff
        price_unit: str = "Kč/kWh",
    ):
        """Initialize coordinator."""
        # Polling only downloads data from the API. The HDO state switch is
        # handled by a dedicated timer scheduled on the next interval boundary.
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=API_UPDATE_INTERVAL,
        )
        self.config_type = config_type
        self.psc = psc
        self.code_a = code_a
        self.code_b = code_b
        self.code_dp = code_dp
        self.hdo_code = hdo_code
        self.price_nt = price_nt
        self.price_vt = price_vt
        self.color_vt = color_vt
        self.color_nt = color_nt
        self.cz_holidays = None
        self.last_successful_update = None
        self.last_update_cached = False
        self.cached_filtered = None
        self.price_unit = price_unit
        self._boundary_unsub: Callable[[], None] | None = None
        self._retry_unsub: Callable[[], None] | None = None

    @staticmethod
    def _now() -> datetime:
        """Return the current time in the HA time zone as a naive datetime (same as HDO intervals)."""
        return dt_util.now().replace(tzinfo=None)

    async def async_shutdown(self) -> None:
        """Cancel own timers and shut the coordinator down."""
        self._cancel_boundary()
        self._cancel_retry()
        await super().async_shutdown()

    def _cancel_boundary(self) -> None:
        if self._boundary_unsub is not None:
            self._boundary_unsub()
            self._boundary_unsub = None

    def _cancel_retry(self) -> None:
        if self._retry_unsub is not None:
            self._retry_unsub()
            self._retry_unsub = None

    def _schedule_boundary(self, data: Dict[str, Any]) -> None:
        """Schedule a recalculation on the next HDO change or midnight, whichever comes first."""
        midnight = dt_util.start_of_local_day(dt_util.now().date() + timedelta(days=1))
        boundary = midnight
        next_change = data.get("next_change")
        if next_change is not None and next_change < midnight:
            boundary = next_change
        self._schedule_recalculation(boundary + BOUNDARY_MARGIN)

    def _schedule_recalculation(self, when: datetime) -> None:
        self._cancel_boundary()
        self._boundary_unsub = async_track_point_in_time(
            self.hass, self._async_boundary_reached, when
        )

    @callback
    def _async_boundary_reached(self, _now: datetime) -> None:
        """Recalculate the HDO state from cached data (no network) and notify entities."""
        self._boundary_unsub = None
        if self.cached_filtered is None:
            return
        try:
            data = self._parse_times(self.cached_filtered, self._now())
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Failed to recalculate HDO state, retrying in 1 minute")
            self._schedule_recalculation(dt_util.now() + timedelta(minutes=1))
            return
        # Don't use async_set_updated_data - it would restart the API polling schedule
        self.data = data
        self.async_update_listeners()
        self._schedule_boundary(data)

    def _schedule_retry(self) -> None:
        self._cancel_retry()
        self._retry_unsub = async_call_later(self.hass, RETRY_DELAY, self._async_retry)

    async def _async_retry(self, _now: datetime) -> None:
        self._retry_unsub = None
        await self.async_refresh()

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from API."""
        
        if self.cz_holidays is None:
            self.cz_holidays = await self.hass.async_add_executor_job(holidays.CZ)
        
        now = self._now()
        
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
                    
                    self.cached_filtered = filtered
                    if not self.last_update_cached:
                        self.last_successful_update = now
                
                # Krok 3: Zparsovat časy z filtrovaných záznamů
                data = self._parse_times(self.cached_filtered, now)
        
        except Exception as err:
            if self.data is not None:
                self._schedule_retry()
            raise UpdateFailed(f"Error fetching data: {err}")

        if self.last_update_cached:
            self._schedule_retry()
        else:
            self._cancel_retry()
        self._schedule_boundary(data)
        return data

    async def _fetch_hdo_data(self, session: aiohttp.ClientSession) -> list:
        """Stáhnout HDO data z API."""
        data, self.last_update_cached = await Download.get_json(
            hass=self.hass,
            session=session,
            url=API_HDO_URL,
            file="hdo",   # uloží se do cache/hdo.json
        )
        return data

    async def _fetch_region(self, session: aiohttp.ClientSession) -> str:
        """Zjistit region z PSČ."""
        data, self.last_update_cached = await Download.get_json(
            hass=self.hass,
            session=session,
            url=API_REGION_URL,
            file="region",   # uloží se do cache/region.json
        )

            
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

    def _parse_times(self, filtered_records: list, now: datetime) -> Dict[str, Any]:
        """Zparsovat HDO časy z filtrovaných záznamů."""
        date_now = now.date()
        date_tomorrow = date_now + timedelta(days=1)
        date_yesterday = date_now - timedelta(days=1)
        date_after_tomorrow = date_now + timedelta(days=2)
        current_month = now.month
        
        hdo_times_yesterday = []
        hdo_times_today = []
        hdo_times_tomorrow = []
        hdo_times_after_tomorrow = []
        
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
                current_year = now.year
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
                    
                    # Včera - potřeba pro noční blok, který začal před půlnocí
                    if self._is_matching_day(date_yesterday, day_code):
                        for cas in day.get('casy', []):
                            hdo_times_yesterday.append({'od': cas['od'], 'do': cas['do']})
                    
                    # Pozítří - potřeba pro konec zítřejšího nočního bloku
                    if self._is_matching_day(date_after_tomorrow, day_code):
                        for cas in day.get('casy', []):
                            hdo_times_after_tomorrow.append({'od': cas['od'], 'do': cas['do']})
                    
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
        
        # Absolutní intervaly sloučené přes půlnoc (např. 20:00-23:59 + 00:00-04:00 = 20:00-04:00)
        intervals = self._build_intervals([
            (date_yesterday, hdo_times_yesterday),
            (date_now, hdo_times_today),
            (date_tomorrow, hdo_times_tomorrow),
            (date_after_tomorrow, hdo_times_after_tomorrow),
        ])
        horizon = datetime.combine(date_after_tomorrow, time(0))
        intervals = [i for i in intervals if i[0] < horizon]
        current_interval = next((i for i in intervals if i[0] <= now < i[1]), None)
        is_in_time_slot = current_interval is not None
        
        # Určit cenu a stav podle typu
        if is_tou:
            # TOU: časy = kdy JE NT
            current_price = self.price_nt if is_in_time_slot else self.price_vt
            # Status: Zapnuto = NT perioda (levná elektřina)
            is_active = is_in_time_slot
        else:
            # Klasické HDO: časy = HDO signál = NT
            current_price = self.price_nt if is_in_time_slot else self.price_vt
            # Status: Zapnuto = HDO signál aktivní
            is_active = is_in_time_slot
        
        next_change = self._get_next_change(now, intervals, current_interval)
        # Naive HA-local time -> tz-aware (the timestamp sensor requires a timezone)
        next_change = next_change.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE) if next_change else None
        
        # Vygenerovat HDO_HOURLY pro dalších 24 hodin
        HDO_HOURLY = self._generate_hdo_hourly(hdo_times_today, hdo_times_tomorrow, now, is_tou)
        
        return {
            "is_active": is_active,
            "hdo_times_today": hdo_times_today,
            "hdo_times_tomorrow": hdo_times_tomorrow,
            "hdo_intervals": [
                {"od": start.isoformat(), "do": end.isoformat()}
                for start, end in intervals
            ],
            "current_price": current_price,
            "next_change": next_change,
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

    def _build_intervals(self, days: list) -> list:
        """Převést sloty (datum, [{'od','do'}]) na seřazené, sloučené datetime intervaly."""
        intervals = []
        for date, slots in days:
            for slot in slots:
                try:
                    start = datetime.combine(date, datetime.strptime(slot['od'], "%H:%M:%S").time())
                    end = datetime.combine(date, datetime.strptime(slot['do'], "%H:%M:%S").time())
                except ValueError:
                    continue
                # API používá xx:59:00 jako konec hodiny (23:59:00 = půlnoc)
                if slot['do'].endswith(':59:00'):
                    end += timedelta(minutes=1)
                if end <= start:
                    end += timedelta(days=1)
                intervals.append((start, end))

        merged = []
        for start, end in sorted(intervals):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return merged

    @staticmethod
    def _get_next_change(now: datetime, intervals: list, current_interval: tuple | None) -> datetime | None:
        """Find the moment of the next HDO change (end of the current interval or start of the next one)."""
        if current_interval is not None:
            return current_interval[1]
        return next((start for start, _ in intervals if start > now), None)

    def _generate_hdo_hourly(self, hdo_times_today: list, hdo_times_tomorrow: list, now: datetime, is_tou: bool = False) -> dict:
        """Vygenerovat HDO_HOURLY atribut - 15minutové intervaly na 48 hodin (dnes + zítra).
        
        Args:
            is_tou: Pokud True, časy jsou invertované (značí kdy JE NT, ne HDO signál)
        """
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
