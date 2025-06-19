from flask import Flask, request, Response, redirect, url_for, render_template
import json
import datetime
import calendar
import pytz
import sqlite3
import importlib
import os
import atexit
import socket
from apscheduler.schedulers.background import BackgroundScheduler
from noaa_sdk import NOAA
from pywebostv.connection import WebOSClient
from pywebostv.controls import ApplicationControl

from classes.db_connect import db_connect
from classes.usps_api_control import USPSApi, SFDCApi, USPSError, SFDCError
from classes.sun_control import sun_control_master
from classes.hbapi_control import hb_authorize, acc_char_data

hbCliHelper = importlib.import_module('homebridgeUIAPI-python.classes.cliHelper')
# from homebridgeUIAPIpython.classes import cliHelp as hbCliHelper

scheduler = BackgroundScheduler()

app = Flask(__name__)

hbAuthFile = "./secrets/hbAuth.json"
uspsAuthFile = "./secrets/uspsAuth.json"
sfdcAuthFile = "./secrets/sfdcAuth.json"
sfdcPrivateKey = "./secrets/private.key"
lgAuthFile = "./secrets/lgtoken.json"

ticktockJob = {"status":"Stopped","job":None,"interval":30}

####################
### Load Secrets ###
####################
secrets = {}
with open(hbAuthFile) as f:
    secrets['hbCreds'] = json.loads(f.read())

with open(uspsAuthFile) as f:
    secrets['uspsCreds'] = json.loads(f.read())

with open(sfdcAuthFile) as f:
    secrets['sfdcCreds'] = json.loads(f.read())

with open(sfdcPrivateKey) as f:
    secrets['sfdcPKey'] = f.read()

###############################################
### Initialize a single database connection ###
###############################################

db_session = db_connect()

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
    secure = request.json.get('secure')

    hb_auth_payload = hb_authorize(host, port, user, passwd, config, secure)

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

############################################
### USPS Informed Delivery Notifications ###
############################################

@app.route('/extract_usps', methods=['GET'])
def extract_ups():
    if request.method == 'GET':

        USPS = USPSApi()
        sesh = USPS.start_session(secrets['uspsCreds']['username'], secrets['uspsCreds']['password'])
        #date = datetime.date(2022, 7, 26)
        todaysMail = USPS.get_mail(sesh)

        SFDC = SFDCApi()
        sfdc_sesh = SFDC.get_sfdc_session(secrets['sfdcCreds']['client_id'], secrets['sfdcCreds']['client_secret'], secrets['sfdcCreds']['refresh_token'], secrets['sfdcCreds']['domain'],  usr=secrets['sfdcCreds']['username'], aud=secrets['sfdcCreds']['audience'], at=secrets['sfdcCreds']['authflow'], key=secrets['sfdcPKey'])

        for mail in todaysMail['mail']:
            r = USPS.download_image(sesh, mail['image'])

            mailId = SFDC.new_mail_item(sfdc_sesh, mail)
            SFDC.upload_mail_image(sfdc_sesh, mail, mailId, r.content)

        if (todaysMail['mail_count'] + todaysMail['package_count']) > 0:
            note = ''

            if todaysMail['mail_count'] > 0:
                note = note + str(todaysMail['mail_count']) + ' mail delivering today. '

            if todaysMail['today_package_count'] > 0:
                note = note + str(todaysMail['today_package_count']) + ' packages delivering today. '

            if todaysMail['package_count'] != todaysMail['today_package_count']:
                note = note + str(todaysMail['package_count']) + ' total packages incoming. '
                    
            SFDC.send_notification(sfdc_sesh, note)

            return note
        else:
            SFDC.send_notification(sfdc_sesh, "No activity today")
            return('no mail')
    else:
        return ('', 204)

###############################################
### Command Override for Blinds Switch Sync ###
###############################################

@app.route('/override_sync', methods=['GET'])
def override_sync():
    if request.method == 'GET':
        db_session.updateSetting(str(request.args.get('state')), 'commandOverride')

        result = {
                'status':'success'
            }

        return json.dumps(result)
    else:
        return ('', 204)

#################################################
### Controls the blinds based on sun position ###
#################################################

@app.route('/sun_control', methods=['GET'])
def sun_control():
    if request.method == 'GET':
        the_sun = sun_control_master(db_session)
        settings = db_session.getSettings()

        #condition = db_session.topConditionFromHistory()
        condition = db_session.topConditionTypeFromHistory()

        shade_state = json.loads(request.args.get('shade_state'))

        now = datetime.datetime.now(tz=pytz.timezone('US/Pacific'))
        nowUTC = datetime.datetime.now(tz=pytz.UTC)

        # test times
        # now = datetime.datetime.now(tz=pytz.timezone('US/Pacific')) - datetime.timedelta (hours=7)
        # nowUTC = datetime.datetime.now(tz=pytz.UTC) - datetime.timedelta (hours=7)

        # get the altitude and azimuth of the sun
        the_sun.get_pos(now)

        db_session.updateSetting(the_sun.alt, 'lastAlt')
        db_session.updateSetting(the_sun.azm, 'lastAzm')

        # use condition passed in from iOS Weather
        # db_session.logCondition(request.args.get('condition'))

        # alternative approach, use lux from the doorbell instead (this needs a better sensor to function)
        #luxString = request.args.get('lux')
        #luxInt = float(luxString.split(" ")[0].replace(",", ""))
        #luxCondition = 'Cloudy' if luxInt < settings['luxThresh'] else 'Clear'
        #db_session.logCondition(luxCondition)

        # another alternative approach, get the weather from the government (very slow update frequency)
        #n = NOAA()
        #weatherSample = n.get_observations_by_lat_lon(the_sun.latitude, the_sun.longitude)
        #for obs in weatherSample:
        #    db_session.logCondition(obs['textDescription'])
        #    break

        weightedSolarThresh = 0

        # solar state weighting logic
        if the_sun.alt < settings['lowerAlt']:
            weightedSolarThresh = settings['solarThresh'] * settings['lowerAltPer']
        elif the_sun.alt > settings['upperAlt']:
            weightedSolarThresh = settings['solarThresh'] * settings['upperAltPer']
        else:
            solarAltWeight = (the_sun.alt - settings['lowerAlt'])/(settings['upperAlt']-settings['lowerAlt'])
            solarAltWeightPer = ((settings['upperAltPer']-settings['lowerAltPer'])*solarAltWeight)+settings['lowerAltPer']
            weightedSolarThresh = settings['solarThresh'] * solarAltWeightPer
            # print(str(weightedSolarThresh) + " " + str(solarAltWeightPer) + " " + str(solarAltWeight))

        # solar state
        solarStatus = int(request.args.get('solar'))
        solarCondition = 'Cloudy' if solarStatus < weightedSolarThresh else 'Clear'
        db_session.logCondition(solarCondition)
        
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

                # check for duration since last change to make sure we're not raising/lowering too frequently
                lastChangeDate = datetime.datetime.fromtimestamp(settings['lastChangeDate'], tz=pytz.UTC)

                diffSinceLastChangeDate = nowUTC - lastChangeDate
                diffSeconds = diffSinceLastChangeDate.total_seconds()
                print(diffSeconds)
                print(settings['lastChangeDate'])


                if diffSeconds > settings['changeBufferDurationSec']:

                    # raise or lower the blinds depending on the weather
                    if condition != settings['lastCondition']:
                        state = ""
                        if condition == "close":
                            if settings['lastCondition'] != "close":
                                result['commands'].append('closeAll')
                                state = 'confirmClose'
                                
                        else:
                            if settings['lastCondition'] == "close":
                                result['commands'].append('raiseAll')
                                state = 'confirmRaise'
                        
                        db_session.updateSetting(state, 'validateShadeState')
                        db_session.updateSetting(condition, 'lastCondition')
                        db_session.updateSetting(calendar.timegm(nowUTC.timetuple()), 'lastChangeDate')
                    
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
    else:
        return ('', 204)

###############################################
### Controls the color of the console light ###
###############################################

@app.route('/console_light')
def console_light():
    if request.method == 'GET':
        store = {}

        if os.path.exists(lgAuthFile):
            with open(lgAuthFile, 'r') as readfile:
                store = json.load(readfile)

        registered = False
        result = {}

        try:
            socket.gethostbyname('LGwebOSTV.dankurtz.local')
            client = WebOSClient('LGwebOSTV.dankurtz.local', secure=True)
            client.connect()
            for status in client.register(store):
                if status == WebOSClient.PROMPTED:
                    print("Please accept the connect on the TV!")
                elif status == WebOSClient.REGISTERED:
                    print("Registration successful!")
                    registered = True
            
            # save store to file
            with open(lgAuthFile, 'w') as outfile:
                json.dump(store, outfile)

            result = {'status':'Not Registered'}

            if registered:
            
                # connect to DB and get ready for queries
                # con = sqlite3.connect('persist.db')
                # cur = con.cursor()
                
                # tv_aid = request.args.get('tv_aid')

                app = ApplicationControl(client)
                tv_aid = app.get_current()

                tvIdMap = {
                    "com.webos.app.hdmi3":"ColorPC",
                    "com.webos.app.hdmi1":"ColorAppleTV",
                    "com.webos.app.hdmi4":"ColorPS4",
                    "com.webos.app.hdmi5":"ColorNintendo"
                }

                result = {
                    'status':'success',
                    'commands':[tvIdMap[tv_aid]]
                }

                client.close()
        except:
            result = {'status':'Error','message':'Could not connect to TV'}

        return json.dumps(result)
    else:
        return ('', 204)

######################
### Admin panel UI ###
######################

@app.route('/')
def adminPanel():
    return render_template('adminPanel.html', get_settings_url=url_for('.getSettingVals'), save_settings_url=url_for('.saveSettingVals'), condition_history_url=url_for('.getConditionHistory'), distinct_conditions_url=url_for('.getDistinctConditions'), ticktock_status_url=url_for('.statusTicktock'), ticktock_start_url=url_for('.startTicktock'), ticktock_stop_url=url_for('.stopTicktock'))

@app.route('/getSettingVals')
def getSettingVals():
    db_session.cur.execute('SELECT name, value FROM settings')
    rs = db_session.cur.fetchall()
    
    result = {}
    if len(rs) > 0:
        for r in rs:
            result[r[0]] = int(r[1]) if r[1].isdigit() else float(r[1]) if is_float(r[1]) else r[1]

    # blatant hack to load the refresh interval to memory from the database
    ticktockJob['interval'] = int(result['ticktockInterval'])

    return json.dumps(result)

def is_float(string):
    try:
        float(string)
        return True
    except ValueError:
        return False

@app.route('/saveSettingVals', methods=["POST"])
def saveSettingVals():
    payload = json.loads(request.data)

    for condition in payload['distinctConditions'].keys():
        db_session.cur.execute('UPDATE distinctConditions SET blindsClosed = ? WHERE condition = ?', (payload['distinctConditions'][condition], condition))

    payload.pop('distinctConditions')

    for setting in payload:
        db_session.cur.execute('UPDATE settings SET value = ?, last_modified = datetime(\'now\') WHERE name = ?', (payload[setting], setting))
        db_session.con.commit()

    # set the commandOverride switch status
    thisExec = hbCliHelper.cliExecutor()

    hb_auth_payload = hb_authorize(secrets['hbCreds']['host'], secrets['hbCreds']['port'], secrets['hbCreds']['username'], secrets['hbCreds']['password'],None,secrets['hbCreds']['secure'])
    authResult = thisExec.authorize(hb_auth_payload)

    # TODO: Need to make the switch name configurable
    override_sync_payload = acc_char_data("Blinds Override", ["On",str(payload['commandOverride'])], authResult['sessionId'])
    thisExec.setaccessorychar(override_sync_payload)

    # set the interval in the current runtime
    ticktockJob['interval'] = int(payload['ticktockInterval'])

    return "{\"status\":\"success\"}"

@app.route('/getConditionHistory')
def getConditionHistory():
    db_session.cur.execute('SELECT condition, timestamp FROM conditionHistory ORDER BY timestamp DESC')
    rs = db_session.cur.fetchall()

    return json.dumps(rs)

@app.route('/getDistinctConditions')
def getDistinctConditions():
    db_session.cur.execute('SELECT condition, blindsClosed FROM distinctConditions ORDER BY condition ASC')
    rs = db_session.cur.fetchall()

    return json.dumps(rs)

@app.route('/getTimeSinceLastCheck')
def getTimeSinceLastCheck():
    db_session.cur.execute('SELECT timestamp, datetime(\'now\') FROM conditionHistory ORDER BY timestamp DESC LIMIT 1')
    rs = db_session.cur.fetchall()

    newestDate = datetime.datetime.strptime(rs[0][0], '%Y-%d-%m %H:%M:%S')
    nowDate = datetime.datetime.strptime(rs[0][1], '%Y-%d-%m %H:%M:%S')

    difference = nowDate - newestDate

    return json.dumps(difference.total_seconds())

def ticktock():
    print("tick")

    thisExec = hbCliHelper.cliExecutor()

    hb_auth_payload = hb_authorize(secrets['hbCreds']['host'], secrets['hbCreds']['port'], secrets['hbCreds']['username'], secrets['hbCreds']['password'],None,secrets['hbCreds']['secure'])
    authResult = thisExec.authorize(hb_auth_payload)

    tick_set_acc_char_payload = acc_char_data("Tick", ["On","1"], authResult['sessionId'])
    light_set_acc_char_payload = acc_char_data("ConsoleLightUpdate", ["On","1"], authResult['sessionId'])

    thisExec.setaccessorychar(tick_set_acc_char_payload)
    thisExec.setaccessorychar(light_set_acc_char_payload)

@app.route('/startTicktock')
def startTicktock():
    scheduler.add_job(ticktock, 'interval', id='ticktock', seconds=ticktockJob['interval'])
    ticktockJob['status'] = "Running"
    if scheduler.state == 0:
        scheduler.start()
    else:
        scheduler.resume()

    ticktock()

    return "{\"status\":\"success\"}"

@app.route('/stopTicktock')
def stopTicktock():
    scheduler.remove_job('ticktock')
    ticktockJob['status'] = "Stopped"
    scheduler.pause()

    return "{\"status\":\"success\"}"

@app.route('/statusTicktock')
def statusTicktock():
    result = {"status":ticktockJob['status']}

    return json.dumps(result)

if __name__ == "__main__":
    app.run(threaded=True)

# Cleanup when the app terminates
@atexit.register
def on_terminate():
    db_session.disconnect()
    print("### Closed the DB Connection ###")

#startTicktock()