from datetime import datetime, timedelta
import holidays


def get_region():
    return "https://hdo.distribuce24.cz/region"


def get_HDO():
    return "https://hdo.distribuce24.cz/casy"


def parse_region(jsonRegion, psc):
    if psc == "smart":
        region = "X"
    else:
        output_region_dict = [x for x in jsonRegion if x['PSC'] == psc]
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
    HDO_HOURLY_TODAY = []
    HDO_HOURLY_TOMORROW = []
    HDO_Status = False

    if HDORegion == "X":
        output_hdo_dict = [x for x in jsonHDO if x['kodHdo_A'] == HDO_A]
    else:
        output_hdo_dict = [x for x in jsonHDO if x['A'] == HDO_A and x['B'] == HDO_B and (
            x['DP'] == HDO_DP or x['DP'] == '0' + HDO_DP) and x['region'] == HDORegion]

    date_now = datetime.now().date()
    date_tomorrow = datetime.now().date() + timedelta(days=1)

    def get_holiday(date):
        cz_holidays = holidays.CZ()  # this is a dict
        return (date in cz_holidays)

    for itemData in output_hdo_dict:
        current_year = datetime.now().year
        if int(itemData['od']['rok']) == 9999:
            if int(itemData['od']['mesic']) < int(itemData['do']['mesic']):
                year = current_year
            else:
                year = current_year + 1
        else:
            year = itemData['od']['rok']

        str_date_time_od = f"{current_year}-{itemData['od']['mesic']}-{itemData['od']['den']}"
        str_date_time_do = f"{year}-{itemData['do']['mesic']}-{itemData['do']['den']}"
        date_time_od_obj = datetime.strptime(
            str_date_time_od, '%Y-%m-%d')
        date_time_do_obj = datetime.strptime(
            str_date_time_do, '%Y-%m-%d')

        if date_time_od_obj.date() <= date_now <= date_time_do_obj.date():
            for tarifs in itemData['sazby']:
                for days in tarifs['dny']:
                    if get_holiday(date_now) == True:
                        if 7 == days['denVTydnu']:
                            for times in days['casy']:
                                HDO_Cas_Od.append(times['od'])
                                HDO_Cas_Do.append(times['do'])
                    else:
                        if date_now.isoweekday() == days['denVTydnu']:
                            for times in days['casy']:
                                HDO_Cas_Od.append(times['od'])
                                HDO_Cas_Do.append(times['do'])

                    if get_holiday(date_tomorrow) == True:
                        if 7 == days['denVTydnu']:
                            for times in days['casy']:
                                HDO_Cas_Od_zitra.append(times['od'])
                                HDO_Cas_Do_zitra.append(times['do'])
                    else:
                        if date_tomorrow.isoweekday() == days['denVTydnu']:
                            for times in days['casy']:
                                HDO_Cas_Od_zitra.append(times['od'])
                                HDO_Cas_Do_zitra.append(times['do'])

            def get_status(time: datetime, od: list, do: list):
                result = False
                compare_time = datetime.strptime(
                    time.strftime('%H:%M:%S'), '%H:%M:%S')

                for x in range(len(od)):
                    HDD_Date_od_obj = datetime.strptime(
                        od[x], '%H:%M:%S')
                    HDD_Date_do_obj = datetime.strptime(
                        do[x], '%H:%M:%S')
                    if HDD_Date_od_obj <= compare_time <= HDD_Date_do_obj:
                        result = True
                return result

            HDO_Status = get_status(
                datetime.now().replace(second=0, microsecond=0), HDO_Cas_Od, HDO_Cas_Do)

            for x in range(0, 24):
                if get_status(datetime.now().replace(
                        hour=x, minute=0, second=0, microsecond=0), HDO_Cas_Od, HDO_Cas_Do):
                    HDO_HOURLY_TODAY.append(HDO_priceNT)
                else:
                    HDO_HOURLY_TODAY.append(HDO_priceVT)

            for x in range(0, 24):
                if get_status(datetime.now().replace(
                        hour=x, minute=0, day=datetime.now().day + 1), HDO_Cas_Od_zitra, HDO_Cas_Do_zitra):
                    HDO_HOURLY_TOMORROW.append(HDO_priceNT)
                else:
                    HDO_HOURLY_TOMORROW.append(HDO_priceVT)

    return HDO_Status, HDO_Cas_Od, HDO_Cas_Do, HDO_HOURLY_TODAY, HDO_HOURLY_TOMORROW
