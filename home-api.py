from flask import Flask, request, Response, redirect, url_for, render_template
import json
import datetime
import pytz
import sqlite3
import importlib
from noaa_sdk import NOAA

from classes.usps_api_control import USPSApi, SFDCApi, USPSError, SFDCError
from classes.sun_control import sun_control_master, db_connect
from classes.hbapi_control import hb_authorize, acc_char_data

hbCliHelper = importlib.import_module('homebridgeUIAPI-python.classes.cliHelper')

app = Flask(__name__)

uspsAuthFile = "./uspsAuth.json"
sfdcAuthFile = "./sfdcAuth.json"

############################################
### USPS Informed Delivery Notifications ###
############################################

@app.route('/extract_usps')
def extract_ups():
    
    with open(uspsAuthFile) as f:
        uspsCreds = json.loads(f.read())

    with open(sfdcAuthFile) as f:
        sfdcCreds = json.loads(f.read())

    USPS = USPSApi()
    sesh = USPS.start_session(uspsCreds['username'], uspsCreds['password'])
    #date = datetime.date(2022, 7, 26)
    todaysMail = USPS.get_mail(sesh)

    SFDC = SFDCApi()
    sfdc_sesh = SFDC.get_sfdc_session(sfdcCreds['client_id'], sfdcCreds['client_secret'], sfdcCreds['refresh_token'], sfdcCreds['domain'])

    for mail in todaysMail:
        r = USPS.download_image(sesh, mail['image'])

        mailId = SFDC.new_mail_item(sfdc_sesh, mail)
        SFDC.upload_mail_image(sfdc_sesh, mail, mailId, r.content)

    if len(todaysMail) > 0:
        note = str(len(todaysMail)) + ' mail incoming'

        SFDC.send_notification(sfdc_sesh, note)

        return note
    else:
        return('no mail')

####################################
### Front-end for homebridge API ###
####################################

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

#################################################
### Controls the blinds based on sun position ###
#################################################

@app.route('/sun_control')
def sun_control():
    db_session = db_connect()
    the_sun = sun_control_master()
    settings = db_session.getSettings()

    n = NOAA()
    # weather broke in iOS 16, can't pass conditions in automation
    #db_session.logCondition(request.args.get('condition'))

    # as a work around, use lux from the doorbell instead (this needs a better sensor to function)
    #luxString = request.args.get('lux')
    #luxInt = float(luxString.split(" ")[0].replace(",", ""))
    #luxCondition = 'Cloudy' if luxInt < settings['luxThresh'] else 'Clear'
    #db_session.logCondition(luxCondition)

    # get the weather from the government
    n = NOAA()
    weatherSample = n.get_observations_by_lat_lon(the_sun.latitude, the_sun.longitude)
    for obs in weatherSample:
        db_session.logCondition(obs['textDescription'])
        break

    #condition = db_session.topConditionFromHistory()
    condition = db_session.topConditionTypeFromHistory()

    shade_state = request.args.get('shade_state')

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
        validateShades = the_sun.validateShadeState(settings['validateShadeState'],shade_state)
        
        if validateShades == None:
            db_session.updateSetting('null', 'validateShadeState')
        else:
            if settings['commandOverride'] != 1:
                result['commands'].append(validateShades)
    
    if settings['commandOverride'] != 1:
        if in_area:
            # raise or lower the blinds depending on the weather
            if condition != settings['lastCondition']:
                if condition == "close":
                    if settings['lastCondition'] != "close":
                        result['commands'].append('closeAll')

                        db_session.updateSetting('confirmClose', 'validateShadeState')
                else:
                    if settings['lastCondition'] == "close":
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

    print(result)
    return json.dumps(result)

###############################################
### Controls the color of the console light ###
###############################################

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

######################
### Admin panel UI ###
######################

@app.route('/')
def adminPanel():
    return render_template('adminPanel.html', get_settings_url=url_for('.getSettingVals'), save_settings_url=url_for('.saveSettingVals'), condition_history_url=url_for('.getConditionHistory'), distinct_conditions_url=url_for('.getDistinctConditions'))

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

@app.route('/saveSettingVals', methods=["POST"])
def saveSettingVals():
    payload = json.loads(request.data)

    updates = {}
    updates['startAzm'] = payload['startAzm']
    updates['endAzm'] = payload['endAzm']
    updates['startAlt'] = payload['startAlt']
    updates['endAlt'] = payload['endAlt']
    updates['conditionHistoryLength'] = payload['conditionHistoryLength']
    updates['commandOverride'] = payload['commandOverride']
    updates['luxThresh'] = payload['luxThresh']

    con = sqlite3.connect('persist.db')
    cur = con.cursor()

    for condition in payload['distinctConditions'].keys():
        cur.execute('UPDATE distinctConditions SET blindsClosed = ? WHERE condition = ?', (payload['distinctConditions'][condition], condition))

    for setting in updates:
        cur.execute('UPDATE settings SET value = ?, last_modified = datetime(\'now\') WHERE name = ?', (updates[setting], setting))
        con.commit()

    con.close()

    return "success"

@app.route('/getConditionHistory')
def getConditionHistory():
    con = sqlite3.connect('persist.db')
    cur = con.cursor()

    cur.execute('SELECT condition, timestamp FROM conditionHistory ORDER BY timestamp DESC')
    rs = cur.fetchall()

    con.close()

    return json.dumps(rs)

@app.route('/getDistinctConditions')
def getDistinctConditions():
    con = sqlite3.connect('persist.db')
    cur = con.cursor()

    cur.execute('SELECT condition, blindsClosed FROM distinctConditions ORDER BY condition ASC')
    rs = cur.fetchall()

    return json.dumps(rs)

@app.route('/getTimeSinceLastCheck')
def getTimeSinceLastCheck():
    con = sqlite3.connect('persist.db')
    cur = con.cursor()

    cur.execute('SELECT timestamp, datetime(\'now\') FROM conditionHistory ORDER BY timestamp DESC LIMIT 1')
    rs = cur.fetchall()

    newestDate = datetime.datetime.strptime(rs[0][0], '%Y-%d-%m %H:%M:%S')
    nowDate = datetime.datetime.strptime(rs[0][1], '%Y-%d-%m %H:%M:%S')

    difference = nowDate - newestDate

    return json.dumps(difference.total_seconds())

if __name__ == "__main__":
    app.run(threaded=True)