import os
import re
import json
import secrets
from datetime import datetime, timedelta

from flask import Flask, render_template, request, session, redirect, send_from_directory

from google.cloud import storage
from google.cloud.exceptions import NotFound

import logging
from logging.config import fileConfig

fileConfig('logger.cfg')
LOGGER = logging.getLogger()

if 'LOG_LEVEL' in os.environ:
    log_levels = {'NOTSET': 0, 'DEBUG': 10, 'INFO': 20,
                  'WARN': 30, 'ERROR': 40, 'CRITICAL': 50}
    if os.environ.get('LOG_LEVEL') in log_levels:
        LOGGER.setLevel(log_levels[os.environ.get('LOG_LEVEL')])
    else:
        LOGGER.error(
            f'LOG_LEVEL {os.environ.get("LOG_LEVEL")} is not a valid level. using {LOGGER.level}')
else:
    LOGGER.warning(f'LOG_LEVEL not set. current log level is {LOGGER.level}')


app_name = 'Airline Manager Website'

app = Flask(app_name, template_folder='templates')

DATE_FORMAT = '%Y-%m-%d'
TIME_FORMAT = '%H:%M:%S %Z'

bucket_name = os.environ.get('BUCKET_NAME', 'cloud-run-am4')
fuel_log_file = os.environ.get('FUEL_LOG_FILE', 'fuel_log.json')


class FuelStats():
    time: str
    fuel_price: int
    co2_price: int
    fuel_low: bool
    co2_low: bool

    def __init__(self, time, fuel_price, co2_price):
        self.time = time
        self.fuel_price = fuel_price
        self.co2_price = co2_price
        self.fuel_low = fuel_price < 600
        self.co2_low = co2_price < 130


def get_fuel_stats():
    return json.loads('{"2022-07-02": {"09:30:00 UTC": {"fuel_price": 1360, "co2_price": 134}, "10:00:00 UTC": {"fuel_price": 1540, "co2_price": 176}, "10:30:00 UTC": {"fuel_price": 1150, "co2_price": 104}, "11:00:00 UTC": {"fuel_price": 930, "co2_price": 122}, "11:30:00 UTC": {"fuel_price": 570, "co2_price": 170}, "12:00:00 UTC": {"fuel_price": 2430, "co2_price": 196}, "12:30:00 UTC": {"fuel_price": 1030, "co2_price": 169}, "13:00:00 UTC": {"fuel_price": 2070, "co2_price": 176}, "13:30:00 UTC": {"fuel_price": 2010, "co2_price": 197}, "14:00:00 UTC": {"fuel_price": 2150, "co2_price": 188}, "14:30:00 UTC": {"fuel_price": 850, "co2_price": 191}, "15:00:00 UTC": {"fuel_price": 840, "co2_price": 111}, "15:30:00 UTC": {"fuel_price": 1880, "co2_price": 165}, "16:00:00 UTC": {"fuel_price": 2370, "co2_price": 188}, "16:30:00 UTC": {"fuel_price": 1810, "co2_price": 119}, "17:00:00 UTC": {"fuel_price": 1140, "co2_price": 152}, "17:30:00 UTC": {"fuel_price": 1640, "co2_price": 197}, "18:00:00 UTC": {"fuel_price": 1760, "co2_price": 125}, "18:30:00 UTC": {"fuel_price": 1360, "co2_price": 103}, "19:00:00 UTC": {"fuel_price": 1850, "co2_price": 200}, "19:30:00 UTC": {"fuel_price": 1860, "co2_price": 153}, "20:00:00 UTC": {"fuel_price": 2320, "co2_price": 100}, "20:30:00 UTC": {"fuel_price": 1970, "co2_price": 160}, "21:00:00 UTC": {"fuel_price": 600, "co2_price": 151}, "21:30:00 UTC": {"fuel_price": 1710, "co2_price": 174}, "22:00:00 UTC": {"fuel_price": 580, "co2_price": 118}, "22:30:00 UTC": {"fuel_price": 1530, "co2_price": 185}, "23:00:00 UTC": {"fuel_price": 570, "co2_price": 174}, "23:30:00 UTC": {"fuel_price": 1260, "co2_price": 176}}, "2022-07-03": {"00:00:00 UTC": {"fuel_price": 1090, "co2_price": 124}, "00:30:00 UTC": {"fuel_price": 460, "co2_price": 187}, "01:00:00 UTC": {"fuel_price": 2050, "co2_price": 117}, "01:30:00 UTC": {"fuel_price": 840, "co2_price": 171}, "02:00:00 UTC": {"fuel_price": 2270, "co2_price": 106}, "04:00:00 UTC": {"fuel_price": 2050, "co2_price": 142}, "04:30:00 UTC": {"fuel_price": 1810, "co2_price": 153}, "05:00:00 UTC": {"fuel_price": 2440, "co2_price": 117}, "05:30:00 UTC": {"fuel_price": 1180, "co2_price": 118}, "06:00:00 UTC": {"fuel_price": 1770, "co2_price": 160}, "06:30:00 UTC": {"fuel_price": 620, "co2_price": 117}, "07:00:00 UTC": {"fuel_price": 420, "co2_price": 153}, "07:30:00 UTC": {"fuel_price": 540, "co2_price": 108}, "08:00:00 UTC": {"fuel_price": 740, "co2_price": 179}, "08:30:00 UTC": {"fuel_price": 1730, "co2_price": 195}, "09:00:00 UTC": {"fuel_price": 370, "co2_price": 144}, "09:30:00 UTC": {"fuel_price": 430, "co2_price": 169}, "10:00:00 UTC": {"fuel_price": 1120, "co2_price": 196}, "10:30:00 UTC": {"fuel_price": 2160, "co2_price": 191}, "11:00:00 UTC": {"fuel_price": 820, "co2_price": 136}, "11:30:00 UTC": {"fuel_price": 2400, "co2_price": 102}, "12:00:00 UTC": {"fuel_price": 940, "co2_price": 134}, "12:30:00 UTC": {"fuel_price": 2440, "co2_price": 177}, "13:00:00 UTC": {"fuel_price": 1950, "co2_price": 106}, "13:30:00 UTC": {"fuel_price": 660, "co2_price": 142}, "14:00:00 UTC": {"fuel_price": 2180, "co2_price": 166}, "14:30:00 UTC": {"fuel_price": 1790, "co2_price": 113}, "15:00:00 UTC": {"fuel_price": 1950, "co2_price": 114}, "15:30:00 UTC": {"fuel_price": 540, "co2_price": 154}, "16:00:00 UTC": {"fuel_price": 510, "co2_price": 129}, "16:30:00 UTC": {"fuel_price": 810, "co2_price": 102}, "17:00:00 UTC": {"fuel_price": 2040, "co2_price": 124}, "17:30:00 UTC": {"fuel_price": 1830, "co2_price": 156}, "18:00:00 UTC": {"fuel_price": 1310, "co2_price": 127}, "18:30:00 UTC": {"fuel_price": 950, "co2_price": 132}, "19:00:00 UTC": {"fuel_price": 2200, "co2_price": 135}, "19:30:00 UTC": {"fuel_price": 1260, "co2_price": 174}, "20:00:00 UTC": {"fuel_price": 1470, "co2_price": 138}, "20:30:00 UTC": {"fuel_price": 2460, "co2_price": 199}, "21:00:00 UTC": {"fuel_price": 1340, "co2_price": 141}, "21:30:00 UTC": {"fuel_price": 1340, "co2_price": 127}, "22:00:00 UTC": {"fuel_price": 1740, "co2_price": 159}, "22:30:00 UTC": {"fuel_price": 1510, "co2_price": 121}, "23:00:00 UTC": {"fuel_price": 630, "co2_price": 138}, "23:30:00 UTC": {"fuel_price": 480, "co2_price": 180}}, "2022-07-04": {"00:00:00 UTC": {"fuel_price": 610, "co2_price": 158}, "00:30:00 UTC": {"fuel_price": 1580, "co2_price": 142}, "01:00:00 UTC": {"fuel_price": 1360, "co2_price": 133}, "01:30:00 UTC": {"fuel_price": 1460, "co2_price": 166}, "02:00:00 UTC": {"fuel_price": 2330, "co2_price": 130}, "02:30:00 UTC": {"fuel_price": 860, "co2_price": 106}, "03:00:00 UTC": {"fuel_price": 350, "co2_price": 132}, "03:30:00 UTC": {"fuel_price": 1220, "co2_price": 148}, "04:00:00 UTC": {"fuel_price": 1160, "co2_price": 138}, "04:30:00 UTC": {"fuel_price": 1900, "co2_price": 175}, "05:00:00 UTC": {"fuel_price": 900, "co2_price": 104}, "05:30:00 UTC": {"fuel_price": 2290, "co2_price": 111}, "06:00:00 UTC": {"fuel_price": 370, "co2_price": 166}, "06:30:00 UTC": {"fuel_price": 1250, "co2_price": 164}, "07:00:00 UTC": {"fuel_price": 1690, "co2_price": 195}, "07:30:00 UTC": {"fuel_price": 2430, "co2_price": 144}, "08:00:00 UTC": {"fuel_price": 1880, "co2_price": 148}, "08:30:00 UTC": {"fuel_price": 2420, "co2_price": 162}}}')
    client = storage.Client()
    bucket = client.get_bucket(bucket_name)
    new_blob = bucket.blob(fuel_log_file)
    try:
        return json.loads(new_blob.download_as_text())
    except NotFound as e:
        LOGGER.exception('Fuel stats file not found in the bucket', e)
        return None


def render_error_template(message):
    return render_template('error.html', title='Error', heading='Ooops!', message=message)


def compute_fuel_stats(fuel_stats_json, timezone_offset, timezone, date):
    previous_day = (datetime.strptime(date, DATE_FORMAT) + timedelta(days=-1)).strftime(DATE_FORMAT)
    next_day = (datetime.strptime(date, DATE_FORMAT) + timedelta(days=1)).strftime(DATE_FORMAT)
    dates = fuel_stats_json.keys()
    if timezone_offset == 0 and date in dates:
        return [FuelStats(time, stat['fuel_price'], stat['co2_price']) for time, stat in fuel_stats_json[date].items()]

    fuel_stats = []
    if date in dates:
        for time, stat in fuel_stats_json[date].items():
            _datetime = datetime.strptime(' '.join([date, time]), ' '.join([DATE_FORMAT, TIME_FORMAT]))
            if timezone_offset < 0:
                _adjusted_datetime = _datetime - timedelta(minutes=timezone_offset)
            else:
                _adjusted_datetime = _datetime + timedelta(minutes=timezone_offset)
            _date = _adjusted_datetime.strftime(DATE_FORMAT)
            if _date != date:
                continue
            _time = _adjusted_datetime.strftime(TIME_FORMAT) + timezone
            fuel_stats.append(FuelStats(_time, stat['fuel_price'], stat['co2_price']))

    if timezone_offset < 0 and previous_day in dates:
        for time, stat in fuel_stats_json[previous_day].items():
            _datetime = datetime.strptime(' '.join([previous_day, time]), ' '.join([DATE_FORMAT, TIME_FORMAT]))
            _adjusted_datetime = _datetime - timedelta(minutes=timezone_offset)
            _date = _adjusted_datetime.strftime(DATE_FORMAT)
            if _date != date:
                continue
            _time = _adjusted_datetime.strftime(TIME_FORMAT) + timezone
            fuel_stats.append(FuelStats(_time, stat['fuel_price'], stat['co2_price']))
    
    if timezone_offset > 0 and next_day in dates:
        for time, stat in fuel_stats_json[next_day].items():
            _datetime = datetime.strptime(' '.join([next_day, time]), ' '.join([DATE_FORMAT, TIME_FORMAT]))
            _adjusted_datetime = _datetime + timedelta(minutes=timezone_offset)
            _date = _adjusted_datetime.strftime(DATE_FORMAT)
            if _date != date:
                continue
            _time = _adjusted_datetime.strftime(TIME_FORMAT) + timezone
            fuel_stats.append(FuelStats(_time, stat['fuel_price'], stat['co2_price']))

    if len(fuel_stats) == 0:
        return None
    
    return fuel_stats


@app.route("/")
def get_status():
    if 'time_zone_offset' not in session:
        session['referrer'] = request.url
        return redirect('/get_tz')
    session.pop("referrer", None)
    fuel_stats_json = get_fuel_stats()
    if fuel_stats_json is None:
        return render_error_template(message='Fuel stats file not found. <br> Please contact me at <a href="mailto:me@aingaran.dev')
    fuel_stats = compute_fuel_stats(fuel_stats_json, session['time_zone_offset'], session['time_zone'], session.get('date', datetime.now().strftime(DATE_FORMAT)))
    if fuel_stats is not None: 
        return render_template('table.html', title='Fuel Statistics', fuel_stats=fuel_stats)
    return render_error_template(message=f'Unable to find fuel stats for today. <br> You can check stats based on date by using the url endpoint <em>"{request.url}yyyy-mm-dd"</em> <br> If you need assistance, please contact me at <a href="mailto:me@aingaran.dev">me@aingaran.dev</a>')


@app.route("/<date>")
def get_status_date(date):
    if 'time_zone_offset' not in session:
        session['referrer'] = request.url
        return redirect('/get_tz')
    session.pop("referrer", None)
    if not re.match(r'\d{4}-\d{2}-\d{2}', date):
        return render_error_template(message=f'Date supplied "{date}" is not of the format yyyy-mm-dd. Please check the date again. <br> if you still need assistance, please contact me at <a href="mailto:me@aingaran.dev')
    fuel_stats_json = get_fuel_stats()
    if fuel_stats_json is None:
        return render_error_template(message='Fuel stats file not found. <br> please contact me at <a href="mailto:me@aingaran.dev')
    fuel_stats = compute_fuel_stats(fuel_stats_json, session['time_zone_offset'], session['time_zone'], date)
    if fuel_stats is not None:
        return render_template('table.html', title='Fuel Statistics', fuel_stats=fuel_stats)
    return render_error_template(message=f'Unable to find fuel stats for the day {date}. <br> You can check stats based on date by using the url endpoint <em>"{request.url}/yyyy-mm-dd"</em> <br> If you need assistance, please contact me at <a href="mailto:me@aingaran.dev">me@aingaran.dev</a>')
    

@app.route("/get_tz")
def get_time_zone():
    LOGGER.debug('getting time zone')
    return render_template('get_tz.html', title='Get Time Zone')


@app.route("/set_tz/<date>/<tz_offset>/<tz>")
def set_time_zone(date, tz_offset, tz):
    LOGGER.debug(f'Setting time zone to {tz} with offset {tz_offset} from UTC and date is {date}')
    session['time_zone_offset'] = int(tz_offset)
    session['time_zone'] = tz
    session['date'] = date
    if 'referrer' in session:
        return redirect(session['referrer'])
    return redirect('/')


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')


if __name__ == "__main__":
    app.secret_key = secrets.token_hex()

    from waitress import serve

    serve(app, host='localhost', port=int(os.environ.get("PORT", 8080)))
