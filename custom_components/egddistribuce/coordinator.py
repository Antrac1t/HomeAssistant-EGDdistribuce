"""Coordinator for EGD Distribuce integration."""
import asyncio
from datetime import datetime, timedelta, time
import logging
from typing import Any, Callable, Dict

import aiohttp
import holidays

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from .const import (
    API_HDO_URL,
    API_REGION_URL,
    CONF_CODE_A,
    CONF_CODE_B,
    CONF_CODE_DP,
    CONF_COLOR_NT,
    CONF_COLOR_VT,
    CONF_CONFIG_TYPE,
    CONF_HDO_CODE,
    CONF_PRICE_NT,
    CONF_PRICE_VT,
    CONF_PSC,
    CONF_SCHEDULE,
    CONFIG_TYPE_CLASSIC,
    CONFIG_TYPE_SMART,
    DEFAULT_COLOR_NT,
    DEFAULT_COLOR_VT,
    DEFAULT_PRICE_NT,
    DEFAULT_PRICE_VT,
    DOMAIN,
)
from .download import get_json
from .schedules import default_schedule, schedule_labels, select_schedule

_LOGGER = logging.getLogger(__name__)

# Traditional HDO schedules treat public holidays as Sundays. Smart schedules
# distinguish holidays by their actual weekday.
HOLIDAY_AS_SUNDAY_REGIONS = ("ZAPAD", "VYCHOD", "VERSACOM")

# How often the HDO schedule is downloaded from the API
API_UPDATE_INTERVAL = timedelta(hours=1)
# Retry delay when the API failed and cached data is being used
RETRY_DELAY = timedelta(minutes=5)
# Margin after an interval boundary so that start <= now < end already holds
BOUNDARY_MARGIN = timedelta(seconds=1)


class EGDDistribuceCoordinator(DataUpdateCoordinator):
    """Coordinator for fetching and parsing EGD HDO data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Initialize coordinator."""
        # Polling only downloads data from the API. The HDO state switch is
        # handled by a dedicated timer scheduled on the next interval boundary.
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=API_UPDATE_INTERVAL,
        )
        # Options (prices, colors) override the values from the initial setup
        config = {**entry.data, **entry.options}
        self.config_type = config.get(CONF_CONFIG_TYPE, CONFIG_TYPE_CLASSIC)
        self.psc = config.get(CONF_PSC)
        self.code_a = config.get(CONF_CODE_A)
        self.code_b = config.get(CONF_CODE_B)
        self.code_dp = config.get(CONF_CODE_DP)
        self.hdo_code = config.get(CONF_HDO_CODE)
        self.price_nt = float(config.get(CONF_PRICE_NT, DEFAULT_PRICE_NT))
        self.price_vt = float(config.get(CONF_PRICE_VT, DEFAULT_PRICE_VT))
        self.color_vt = str(config.get(CONF_COLOR_VT, DEFAULT_COLOR_VT))
        self.color_nt = str(config.get(CONF_COLOR_NT, DEFAULT_COLOR_NT))
        self.cz_holidays = None
        self.last_successful_update = None
        self.last_update_cached = False
        self.cached_filtered = None
        currency = hass.config.currency
        self.price_unit = f"{'Kč' if currency == 'CZK' else currency}/kWh"
        self.schedule = config.get(CONF_SCHEDULE)
        self.entry_id = entry.entry_id
        # "ok", "default" (no choice saved, several schedules) or "missing" (saved schedule is gone)
        self.schedule_status = "ok"
        self.active_schedule = None
        self._boundary_unsub: Callable[[], None] | None = None

    @staticmethod
    def _now() -> datetime:
        """Return the current time in the HA time zone as a naive datetime (same as HDO intervals)."""
        return dt_util.now().replace(tzinfo=None)

    async def async_shutdown(self) -> None:
        """Cancel own timers and shut the coordinator down."""
        self._cancel_boundary()
        await super().async_shutdown()

    def _cancel_boundary(self) -> None:
        if self._boundary_unsub is not None:
            self._boundary_unsub()
            self._boundary_unsub = None

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

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from API."""
        
        if self.cz_holidays is None:
            self.cz_holidays = await self.hass.async_add_executor_job(holidays.CZ)
        
        now = self._now()
        
        try:
            async with asyncio.timeout(30):
                session = async_get_clientsession(self.hass)
                # Krok 1: Stáhnout HDO data
                hdo_data, cached = await self._fetch_hdo_data(session)

                # Krok 2: Najít relevantní záznamy podle typu konfigurace
                if self.config_type == CONFIG_TYPE_SMART:
                    filtered = self._filter_smart(hdo_data)
                else:
                    region, region_cached = await self._fetch_region(session)
                    cached = cached or region_cached
                    if self.config_type == CONFIG_TYPE_CLASSIC:
                        filtered = self._filter_classic(hdo_data, region)
                    else:  # CONFIG_TYPE_HDO_CODES
                        filtered = self._filter_hdo_codes(hdo_data, region)

                self.cached_filtered = filtered
                self.last_update_cached = cached
                if not cached:
                    self.last_successful_update = now

                # Krok 3: Zparsovat časy z filtrovaných záznamů
                data = self._parse_times(self.cached_filtered, now)
        
        except Exception as err:
            self.update_interval = RETRY_DELAY
            raise UpdateFailed(f"Error fetching data: {err}")

        # Retry sooner while running on cached data
        self.update_interval = RETRY_DELAY if self.last_update_cached else API_UPDATE_INTERVAL
        self._sync_schedule_issue()
        self._schedule_boundary(data)
        return data

    async def _fetch_hdo_data(self, session: aiohttp.ClientSession) -> tuple[list, bool]:
        """Stáhnout HDO data z API. Vrací (data, z_cache)."""
        return await get_json(
            hass=self.hass,
            session=session,
            url=API_HDO_URL,
            file="hdo",   # uloží se do cache/hdo.json
        )

    async def _fetch_region(self, session: aiohttp.ClientSession) -> tuple[str, bool]:
        """Zjistit region z PSČ. Vrací (region, z_cache)."""
        data, cached = await get_json(
            hass=self.hass,
            session=session,
            url=API_REGION_URL,
            file="region",   # uloží se do cache/region.json
        )

        region_records = [x for x in data if x.get('PSC') == self.psc]
        if not region_records:
            raise UpdateFailed(f"Region not found for PSČ: {self.psc}")
        
        # Vrátit první unikátní region
        return region_records[0]['Region'], cached

    def _filter_classic(self, hdo_data: list, region: str) -> list:
        """VARIANTA 1: Classic - PSČ + A + B + DP"""
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

    def _filter_hdo_codes(self, hdo_data: list, region: str) -> list:
        """VARIANTA 2: HDO Codes - PSČ + seznam kódů (405,406,410)"""
        codes = [c.strip() for c in self.hdo_code.split(',')]
        
        _LOGGER.debug(f"HDO Codes filter: region={region}, codes={codes}")
        
        filtered = [
            x for x in hdo_data
            if x.get('region') == region and x.get('kodHdo_A') in codes
        ]

        _LOGGER.debug(f"HDO Codes filter: found {len(filtered)} records")
        return filtered

    def _filter_smart(self, hdo_data: list) -> list:
        """VARIANTA 3: Smart - jen kodHdo_A (Cd56), žádný region"""
        _LOGGER.debug(f"Smart filter: code={self.hdo_code}")
        
        filtered = [
            x for x in hdo_data
            if x.get('kodHdo_A') == self.hdo_code
        ]

        # A smart code can include separate relay schedules (e.g. PV and TUV)
        # that must not be mixed together.
        labels = schedule_labels(filtered)
        if self.schedule in labels:
            selected = self.schedule
            self.schedule_status = "ok"
        else:
            selected = default_schedule(labels)
            if self.schedule:
                self.schedule_status = "missing"
            else:
                self.schedule_status = "default" if len(labels) > 1 else "ok"
        self.active_schedule = selected
        if selected is not None:
            filtered = select_schedule(filtered, selected)
        
        _LOGGER.debug(
            f"Smart filter: found {len(filtered)} records, schedule={selected}, status={self.schedule_status}"
        )
        return filtered

    def _sync_schedule_issue(self) -> None:
        """Tell the user when the schedule was chosen automatically or is no longer offered."""
        if self.entry_id is None or self.config_type != CONFIG_TYPE_SMART:
            return
        issue_id = f"smart_schedule_{self.entry_id}"
        if self.schedule_status == "ok":
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            return
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=f"smart_schedule_{self.schedule_status}",
            translation_placeholders={
                "code": str(self.hdo_code),
                "schedule": str(self.active_schedule),
            },
        )

    def _parse_times(self, filtered_records: list, now: datetime) -> Dict[str, Any]:
        """Zparsovat HDO časy z filtrovaných záznamů."""
        date_now = now.date()
        date_tomorrow = date_now + timedelta(days=1)
        date_yesterday = date_now - timedelta(days=1)
        date_after_tomorrow = date_now + timedelta(days=2)
        current_month = now.month
        
        # Včera (noční blok začatý před půlnocí) až pozítří (konec zítřejšího nočního bloku)
        times_by_date = {
            date_yesterday: [],
            date_now: [],
            date_tomorrow: [],
            date_after_tomorrow: [],
        }
        
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
            holiday_as_sunday = record.get("region") in HOLIDAY_AS_SUNDAY_REGIONS
            for sazba in record.get('sazby', []):
                for day in sazba.get('dny', []):
                    day_code = day['denVTydnu']
                    for date, slots in times_by_date.items():
                        if self._is_matching_day(date, day_code, holiday_as_sunday):
                            slots.extend(
                                {'od': cas['od'], 'do': cas['do']}
                                for cas in day.get('casy', [])
                            )
        
        hdo_times_today = sorted(times_by_date[date_now], key=lambda x: x['od'])
        hdo_times_tomorrow = sorted(times_by_date[date_tomorrow], key=lambda x: x['od'])
        
        _LOGGER.debug(f"Found {len(hdo_times_today)} slots today, {len(hdo_times_tomorrow)} tomorrow")
        
        # Získat region z prvního záznamu (pokud existuje)
        region = filtered_records[0].get('region', 'N/A') if filtered_records else 'N/A'
        
        # Absolutní intervaly sloučené přes půlnoc (např. 20:00-23:59 + 00:00-04:00 = 20:00-04:00)
        intervals = self._build_intervals(list(times_by_date.items()))
        horizon = datetime.combine(date_after_tomorrow, time(0))
        intervals = [i for i in intervals if i[0] < horizon]
        current_interval = next((i for i in intervals if i[0] <= now < i[1]), None)
        is_in_time_slot = current_interval is not None
        
        # Časy z API značí NT: u klasického HDO signál, u TOU levnou periodu
        current_price = self.price_nt if is_in_time_slot else self.price_vt
        is_active = is_in_time_slot
        
        next_change = self._get_next_change(now, intervals, current_interval)
        # Naive HA-local time -> tz-aware (the timestamp sensor requires a timezone)
        next_change = next_change.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE) if next_change else None
        
        # Ceny po 15 minutách pro dnešek a zítřek
        HDO_HOURLY = self._generate_hdo_hourly(intervals, now)
        
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
            # HA local date the schedule was computed for (today/tomorrow refer to it)
            "date_today": date_now.isoformat(),
            "HDO_HOURLY": HDO_HOURLY,
        }

    def _is_matching_day(
        self, date: datetime.date, day_code: int, holiday_as_sunday: bool
    ) -> bool:
        """Check whether a date matches a schedule weekday and its holiday rules."""
        if holiday_as_sunday and date in self.cz_holidays:
            return day_code == 7
        return date.isoweekday() == day_code

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

    def _generate_hdo_hourly(self, intervals: list, now: datetime) -> dict:
        """Ceny po 15 minutách na 48 hodin (dnes + zítra) ze sloučených intervalů."""
        start = datetime.combine(now.date(), time(0))
        result = {}
        for i in range(2 * 96):
            # Klíč je naivní datetime - kompatibilní se starou verzí
            timestamp = start + timedelta(minutes=i * 15)
            in_slot = any(begin <= timestamp < end for begin, end in intervals)
            result[timestamp] = float(self.price_nt if in_slot else self.price_vt)
        return result
