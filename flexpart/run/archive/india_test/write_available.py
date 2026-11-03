#!/usr/bin/env python3

import argparse
from datetime import datetime, timedelta

def make_datelist(startdate, stopdate, step=timedelta(hours=1)):
    """
    constructs a list of dates
    startdate: starting date in datetime format
    stopdate: stopping date in datetime format
    step: difference between dates as datetime.timedelta
    """
    datelist = []
    date = startdate
    while date <= stopdate:
        datelist.append(date)
        date += step

    return datelist

parser = argparse.ArgumentParser(description='Writes an AVAILABLE file for FLEXPART')

parser.add_argument('startdate', help='first date in the available file (YYYYMMDD)')
parser.add_argument('stopdate', help='last date in the available file (YYYYMMDD)')
parser.add_argument('--dateformat', help='dateformat in the filenames', nargs='?', default='%Y%m%d%H')
parser.add_argument('--prefix', help='everything that comes before the date in the filenames', nargs='?', default='%Y/%m/EA')
parser.add_argument('--suffix', help='everything that comes after the date in the filenames', nargs='?', default='')
parser.add_argument('--timestep', help='timestep of the files in hours', nargs='?', default='1')

args = parser.parse_args()

timestep = int(args.timestep)
startdate = datetime.strptime(args.startdate, '%Y%m%d')
stopdate = datetime.strptime(args.stopdate, '%Y%m%d')

datelist = make_datelist(startdate, stopdate, step=timedelta(hours=timestep))

with open('AVAILABLE', mode='w') as f:
    f.write('XXXXXX EMPTY LINES XXXXXXXX\n')
    f.write('XXXXXX EMPTY LINES XXXXXXXX\n')
    f.write('YYYYMMDD HHMMSS   name of the file(up to 80 characters)\n')
    for date in datelist:
        if args.suffix == 'CFSv2': # suffix depends on date
            suffix = '00.cdas1.'+(date - timedelta(hours=6)).strftime('%Y%m%d')+'.combined.grb2'
        else:
            suffix = args.suffix
        f.write(date.strftime('%Y%m%d %H%M%S')+'      '+\
            date.strftime(args.prefix+args.dateformat+suffix)+'      ON DISK\n')
