import json
import datetime
import holidays
import requests
from urllib.request import urlopen

def getRegion():
    return "https://hdo.distribuce24.cz/region"

def getHDO():
    return "https://hdo.distribuce24.cz/casy"

def getHoliday():
    cz_holidays = holidays.CZ()  # this is a dict
    dateNow = datetime.datetime.now().date()
    return (dateNow in cz_holidays)

def parseRegion(jsonRegion,psc):
    #input_region_dict = json.load(regionFile )
    output_region_dict = [x for x in jsonRegion if x['PSC'] == psc]
    unique_region_list = []
    for itemRegion in output_region_dict:  
        if itemRegion['Region'] not in unique_region_list:
            unique_region_list.append(itemRegion['Region'])
    return unique_region_list[0]

def parseHDO(jsonHDO,HDORegion,HDO_A,HDO_B,HDO_DP):
    HDO_Date_Od=[]
    HDO_Date_Do=[]
    HDO_Cas_Od = []
    HDO_Cas_Do = []
    dateNow = datetime.datetime.now().date()
    dateNowTime = datetime.datetime.now()
    #roll back
    rounded_now = dateNowTime.replace(second=0, microsecond=0)

    if len(HDORegion) == 2:
        dateNow = dateNow.replace(year=9999)
        output_hdo_dict = [x for x in jsonHDO if x['skupinaPovelu'] == HDO_A and x['region'] == HDORegion]    
    else:
        output_hdo_dict = [x for x in jsonHDO if x['A'] == HDO_A and x['B'] == HDO_B and (x['DP'] == HDO_DP or x['DP'] == '0' + HDO_DP) and x['region'] == HDORegion]
        


    HDOStatus=False

    isCZHoliday=getHoliday()

    
    for itemData in output_hdo_dict:
        str_date_time_od = itemData['od']['rok'] + "-" + itemData['od']['mesic'] + "-" + itemData['od']['den']
        str_date_time_do = itemData['do']['rok'] + "-" + itemData['do']['mesic'] + "-" + itemData['do']['den']
        date_time_od_obj = datetime.datetime.strptime(str_date_time_od, '%Y-%m-%d')
        date_time_do_obj = datetime.datetime.strptime(str_date_time_do, '%Y-%m-%d')

        if date_time_od_obj.date() <= dateNow <= date_time_do_obj.date():
            HDO_Date_Od=(str_date_time_od )   
            HDO_Date_Do=(str_date_time_do )
            for itemDataSazby in itemData['sazby']:
                HDO_Sazba = (itemDataSazby['sazba'])
                for itemDataDny in itemDataSazby['dny']:
                    if isCZHoliday == True:
                        if 7 == itemDataDny['denVTydnu']:
                            for itemDataCasy in itemDataDny['casy']:
                                HDO_Cas_Od.append(itemDataCasy['od'])
                                HDO_Cas_Do.append(itemDataCasy['do'])
                    else:    
                        if dateNow.isoweekday() == itemDataDny['denVTydnu']:
                            for itemDataCasy in itemDataDny['casy']:
                                HDO_Cas_Od.append(itemDataCasy['od'])
                                HDO_Cas_Do.append(itemDataCasy['do'])

            for x in range(len(HDO_Cas_Od)):
                HDD_Date_od_obj = datetime.datetime.strptime(HDO_Cas_Od[x], '%H:%M:%S')
                HDD_Date_do_obj = datetime.datetime.strptime(HDO_Cas_Do[x], '%H:%M:%S')
                #roll back timeNow = datetime.datetime.strptime(dateNowTime.strftime('%H:%M:%S'), '%H:%M:%S')
                timeNow = datetime.datetime.strptime(rounded_now.strftime('%H:%M:%S'), '%H:%M:%S')
                if HDD_Date_od_obj <= timeNow <= HDD_Date_do_obj:
                    HDOStatus=True
    return HDOStatus,HDO_Cas_Od,HDO_Cas_Do;
    #return(HDOStatus)
