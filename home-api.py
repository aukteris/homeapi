from flask import Flask, request, Response, redirect, url_for, render_template
import json
import datetime
import pytz
import sqlite3
import importlib

from classes.sun_control import sun_control_master, db_connect
from classes.hbapi_control import hb_authorize, acc_char_data

hbCliHelper = importlib.import_module('homebridgeUIAPI-python.classes.cliHelper')

app = Flask(__name__)

@app.route('/extract_usps')
def extract_ups():

    pass

### Front-end for homebridge API ###
@app.route('/hbapi/auth', methods=['POST'])
def hb_auth():
    host = request.json.get('host')
    port = request.json.get('port')
    user = request.json.get('user')
    passwd = request.json.get('passwd')
    config = request.json.get('config')

    hb_auth_payload = hb_authorize(host, port, user, passwd, config)

    thisExec = hbCliHelper.cliExecutor()
    result = thisExec.authorize(hb_auth_payload)

    return json.dumps(result)

@app.route('/hbapi/setaccessorychar', methods=['POST'])
def set_acc_char():
    name = request.json.get('name')
    chars = [request.json.get('type'),request.json.get('value')]
    session = request.headers.get('sessionId')

    set_acc_char_payload = acc_char_data(name, chars, session)

    thisExec = hbCliHelper.cliExecutor()
    result = thisExec.setaccessorychar(set_acc_char_payload)

    return json.dumps(result)

@app.route('/hbapi/getaccessorycharvals', methods=['POST'])
def get_acc_chars():
    name = request.json.get('name')
    chars = [request.json.get('type')]
    session = request.headers.get('sessionId')

    get_acc_char_payload = acc_char_data(name,chars,session)

    thisExec = hbCliHelper.cliExecutor()
    result = thisExec.accessorycharvalues(get_acc_char_payload)

    return json.dumps(result)

@app.route('/hbapi/listaccessorychars', methods=['POST'])
def list_acc_chars():
    name = request.json.get('name')
    session = request.headers.get('sessionId')

    list_acc_char_payload = acc_char_data(name,None,session)

    thisExec = hbCliHelper.cliExecutor()
    result = thisExec.listaccessorychars(list_acc_char_payload)

    return json.dumps(result)

### Controls the blinds based on sun position ###
@app.route('/sun_control')
def sun_control():
    condition = request.args.get('condition')
    shade_state = request.args.get('shade_state')

    the_sun = sun_control_master()
    db_session = db_connect()

    settings = db_session.getSettings()
    now = datetime.datetime.now(tz=pytz.timezone('US/Pacific'))

    # get the altitude and azimuth of the sun
    the_sun.get_pos(now)
    db_session.updateSetting(the_sun.alt, 'lastAlt')
    db_session.updateSetting(the_sun.azm, 'lastAzm')
    
    in_area = the_sun.sunInArea(the_sun.azm, the_sun.alt, settings['startAzm'], settings['endAzm'], settings['startAlt'], settings['endAlt'])

    result = {
        'status':'success',
        'commands':[]
    }

    # logic to retry shade commands if the blinds aren't in the correct state
    if settings['validateShadeState'] != 'null' and (condition == settings['lastCondition'] or settings['lastCondition'] == 'null'):
        validateShades = the_sun.validateShadeState(settings['validateShadeState'])
        
        if validateShades == None:
            db_session.updateSetting('null', 'validateShadeState')
        else:
            result['commands'].append(validateShades)

    if in_area:
        # raise or lower the blinds depending on the weather
        if condition != settings['lastCondition']:
            if condition in the_sun.lowerConditions:
                if settings['lastCondition'] not in the_sun.lowerConditions:
                    result['commands'].append('closeAll')

                    db_session.updateSetting('confirmClose', 'validateShadeState')
            else:
                if settings['lastCondition'] in the_sun.lowerConditions:
                    result['commands'].append('raiseAll')

                    db_session.updateSetting('confirmRaise', 'validateShadeState')
    
            db_session.updateSetting(condition, 'lastCondition')
        
        db_session.updateSetting('true','lastInArea')

    else:
        # if the last update position was within the watch area, raise the blinds
        if settings['lastInArea'] == 'true':
            if settings['lastCondition'] != "null":
                result['commands'].append('raiseAll')

                db_session.updateSetting('null', 'lastCondition')
                db_session.updateSetting('confirmRaise', 'validateShadeState')
        
        db_session.updateSetting('false','lastInArea')

    return json.dumps(result)

### Controls the color of the console light ###
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
        'status':'success',
        'commands':[tvIdMap[tv_aid]]
    }

    return json.dumps(result)


### Admin panel ###
@app.route('/')
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