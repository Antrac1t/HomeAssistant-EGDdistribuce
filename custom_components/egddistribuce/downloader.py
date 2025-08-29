# downloader.py

from datetime import datetime, timedelta, time
import holidays
from typing import Dict
import logging
from zoneinfo import ZoneInfo

_LOGGER = logging.getLogger(__name__)

cz_holidays = holidays.CZ()

def get_region():
    return "https://hdo.distribuce24.cz/region"

def get_HDO():
    return "https://hdo.distribuce24.cz/casy"

def parse_region(jsonRegion, psc):
    if psc == "smart":
        region = "X"
    else:
        output_region_dict = [x for x in jsonRegion if x['PSC'] == psc]
        if not output_region_dict:
            _LOGGER.warning(f"Region not found for PSC: {psc}")
            return None
        unique_region_list = []
        for item_region in output_region_dict:
            if item_region['Region'] not in unique_region_list:
                unique_region_list.append(item_region['Region'])
        region = unique_region_list[0]
    return region

def parse_HDO(jsonHDO, HDORegion, HDO_A, HDO_B, HDO_DP, HDO_priceNT, HDO_priceVT):
    HDO_Cas_Od = []
    HDO_Cas_Do = []
    HDO_Cas_Od_zitra = []
    HDO_Cas_Do_zitra = []
    HDO_HOURLY: Dict[datetime, float] = {}
    HDO_Status = False
    price = HDO_priceVT

    zoneinfo = ZoneInfo(self.hass.config.time_zone)

    if HDORegion is None:
        _LOGGER.error("Region is None. Cannot parse HDO data.")
        return False, [], [], {}, HDO_priceVT

    if HDORegion == "X":
        output_hdo_dict = [x for x in jsonHDO if x['kodHdo_A'] == HDO_A]
    else:
        output_hdo_dict = [x for x in jsonHDO if x['A'] == HDO_A and x['B'] == HDO_B and (
                x['DP'] == HDO_DP or x['DP'] == '0' + HDO_DP) and x['region'] == HDORegion]

    date_now = datetime.now().date()
    date_tomorrow = datetime.now().date() + timedelta(days=1)

    def get_holiday(date):
        return (date in cz_holidays)

    for itemData in output_hdo_dict:
        current_year = datetime.now().year
        od_year = int(itemData['od']['rok'])

        if od_year < current_year and int(itemData['od']['mesic']) > datetime.now().month:
            current_year = current_year - 1
        
        do_year = int(itemData['do']['rok'])
        if do_year < od_year:
             do_year = do_year + 1

        str_date_time_od = f"{current_year}-{itemData['od']['mesic']}-{itemData['od']['den']}"
        str_date_time_do = f"{do_year}-{itemData['do']['mesic']}-{itemData['do']['den']}"
        
        try:
            date_time_od_obj = datetime.strptime(str_date_time_od, '%Y-%m-%d')
            date_time_do_obj = datetime.strptime(str_date_time_do, '%Y-%m-%d')
        except ValueError as e:
            _LOGGER.warning(f"Could not parse date {str_date_time_od} or {str_date_time_do}: {e}")
            continue

        if date_time_od_obj.date() <= date_now <= date_time_do_obj.date():
            for tarifs in itemData['sazby']:
                for days in tarifs['dny']:
                    is_holiday = get_holiday(date_now)
                    if (is_holiday and days['denVTydnu'] == 7) or (not is_holiday and date_now.isoweekday() == days['denVTydnu']):
                        for times in days['casy']:
                            HDO_Cas_Od.append(times['od'])
                            HDO_Cas_Do.append(times['do'])
                    
                    is_holiday_tomorrow = get_holiday(date_tomorrow)
                    if (is_holiday_tomorrow and days['denVTydnu'] == 7) or (not is_holiday_tomorrow and date_tomorrow.isoweekday() == days['denVTydnu']):
                        for times in days['casy']:
                            HDO_Cas_Od_zitra.append(times['od'])
                            HDO_Cas_Do_zitra.append(times['do'])

    today_pairs = sorted(zip(HDO_Cas_Od, HDO_Cas_Do))
    HDO_Cas_Od = [p[0] for p in today_pairs]
    HDO_Cas_Do = [p[1] for p in today_pairs]
    
    tomorrow_pairs = sorted(zip(HDO_Cas_Od_zitra, HDO_Cas_Do_zitra))
    HDO_Cas_Od_zitra = [p[0] for p in tomorrow_pairs]
    HDO_Cas_Do_zitra = [p[1] for p in tomorrow_pairs]
    
    def get_status(time_to_check: datetime, od: list, do: list):
        result = False
        compare_time = datetime.strptime(time_to_check.strftime('%H:%M:%S'), '%H:%M:%S')

        for x in range(len(od)):
            HDD_Date_od_obj = datetime.strptime(od[x], '%H:%M:%S')
            HDD_Date_do_obj = datetime.strptime(do[x], '%H:%M:%S')

            if do[x].endswith(':59:00'):
                HDD_Date_do_obj = HDD_Date_do_obj + timedelta(minutes=1)
            
            if HDD_Date_od_obj <= compare_time < HDD_Date_do_obj:
                result = True
        return result

    HDO_Status = get_status(datetime.now().replace(second=0, microsecond=0), HDO_Cas_Od, HDO_Cas_Do)
    if HDO_Status:
        price = HDO_priceNT

    for x in range(0, (24*4)):
        date = datetime.combine(date_now, time=time(
            hour=0)) + timedelta(minutes=x*15)

        dateIso = (datetime.combine(date_now, time=time(
            hour=0), tzinfo=zoneinfo) + timedelta(minutes=x*15))

        if get_status(date, HDO_Cas_Od, HDO_Cas_Do):
            HDO_HOURLY[dateIso] = float(HDO_priceNT)
        else:
            HDO_HOURLY[dateIso] = float(HDO_priceVT)

    for x in range(0, (24*4)):
        date = datetime.combine(date_tomorrow, time=time(
            hour=0)) + timedelta(minutes=x*15)

        dateIso = (datetime.combine(date_tomorrow, time=time(
            hour=0), tzinfo=zoneinfo) + timedelta(minutes=x*15))

        if get_status(date, HDO_Cas_Od_zitra, HDO_Cas_Do_zitra):
            HDO_HOURLY[dateIso] = float(HDO_priceNT)
        else:
            HDO_HOURLY[dateIso] = float(HDO_priceVT)
    
    return HDO_Status, HDO_Cas_Od, HDO_Cas_Do, HDO_HOURLY, price, HDO_Cas_Od_zitra, HDO_Cas_Do_zitra



