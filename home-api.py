from flask import Flask, request, Response, redirect, url_for, render_template
import json
import datetime
import pytz
import sqlite3

from sun_control import sun_control_master
from pysolar import solar


app = Flask(__name__)

@app.route('/')
def root():

    return "hi"

@app.route('/extract_usps')
def extract_ups():

    pass

@app.route('/sun_control')
def sun_control():
    conditon = request.args.get('condition')
    shade_state = request.args.get('shade_state')

    the_sun = sun_control_master()
    settings = the_sun.getSettings()
    now = datetime.datetime.now(tz=pytz.timezone('US/Pacific'))

    # get the altitude and azimuth of the sun
    sun_alt = solar.get_altitude(the_sun.latitude, the_sun.longitude, now)
    sun_azm = solar.get_azimuth(the_sun.latitude, the_sun.longitude, now)
    the_sun.updateSetting(sun_alt, 'lastAlt')
    the_sun.updateSetting(sun_azm, 'lastAzm')
    
    in_area = the_sun.sunInArea(sun_azm, sun_alt, settings['startAzm'], settings['endAzm'], settings['startAlt'], settings['endAlt'])

    result = {
        'status':';success',
        'commands':[]
    }

    # logic to retry shade commands if the blinds aren't in the correct state
    if settings['validateShadeState'] != 'null' and (condition == settings['lastCondition'] or settings['lastCondition'] == 'null'):
        if settings['validateShadeState'] == 'confirmRaise':
            if shade_state != '100':
                result['commands'].append('raiseAll')
            else:
                the_sun.updateSetting('null', 'validateShadeState')
                            
        if settings['validateShadeState'] == 'confirmClose':
            if shade_state != '0':
                result['commands'].append('closeAll')
            else:
                the_sun.updateSetting('null', 'validateShadeState')

    if in_area:
        # raise or lower the blinds depending on the weather
        if condition != settings['lastCondition']:
            if condition in lowerConditions:
                if settings['lastCondition'] not in lowerConditions:
                    result['commands'].append('closeAll')

                    the_sun.updateSetting('confirmClose', 'validateShadeState')
            else:
                if settings['lastCondition'] in lowerConditions:
                    result['commands'].append('raiseAll')

                    the_sun.updateSetting('confirmRaise', 'validateShadeState')
    
            the_sun.updateSetting(args.condition, 'lastCondition')
        
        the_sun.updateSetting('true','lastInArea')

    else:
        # if the last update position was within the watch area, raise the blinds
        if settings['lastInArea'] == 'true':
            if settings['lastCondition'] != "null":
                result['commands'].append('raiseAll')

                the_sun.updateSetting('null', 'lastCondition')
                the_sun.updateSetting('confirmRaise', 'validateShadeState')
        
        the_sun.updateSetting('false','lastInArea')

    return json.dumps(result)
    
@app.route('/console_light')
def console_light():
    tv_aid = request.args.get('tv_aid')

    tvIdMap = {
        "5":"ColorPC",
        "3":"ColorAppleTV",
        "4":"ColorPS4",
        "6":"ColorNintendo"
    }

    result = {
        'status':';success',
        'commands':[tvIdMap[tv_aid]]
    }

    return "hi"

@app.route('/admin')
def adminPanel():
    return render_template('adminPanel.html', get_settings_url=url_for('.getSettingVals'), save_settings_url=url_for('.saveSettingVals'))

@app.route('/getSettingVals')
def getSettingVals():
    con = sqlite3.connect('persist.db')
    cur = con.cursor()

    cur.execute('SELECT name, value FROM settings')
    rs = cur.fetchall()

    result = {}
    if len(rs) > 0:
        for r in rs:
            result[r[0]] = int(r[1]) if r[1].isdigit() else r[1]

    con.close()

    return json.dumps(result)

@app.route('/saveSettingVals')
def saveSettingVals():
    updates = {}
    updates['startAzm'] = request.args.get('startAzm')
    updates['endAzm'] = request.args.get('endAzm')
    updates['startAlt'] = request.args.get('startAlt')
    updates['endAlt'] = request.args.get('endAlt')

    con = sqlite3.connect('persist.db')
    cur = con.cursor()

    for setting in updates:
        cur.execute('UPDATE settings SET value = ?, last_modified = datetime(\'now\') WHERE name = ?', (updates[setting], setting))
        con.commit()

    con.close()

    return "success"

if __name__ == "__main__":
    app.run(threaded=True)