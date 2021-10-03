import sqlite3
from pysolar import solar

class db_connect:
    def __init__(self):
        self.settingDefaults = {
            'lastCondition':'null',
            'validateShadeState':'null',
            'startAzm':100,
            'endAzm':260,
            'startAlt':15,
            'endAlt':15,
            'lastInArea':'false',
            'lastAzm':'null',
            'lastAlt':'null'
        }
        
        # connect to DB and get ready for queries
        self.con = sqlite3.connect('persist.db')
        self.cur = self.con.cursor()

        self._init_db()

    def _init_db(self):
        self.cur.execute('CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, value TEXT, last_modified TEXT)')

        for s in self.settingDefaults:
            values = {"settingName":s,"defaultValue":self.settingDefaults[s]}

            self.cur.execute('SELECT id FROM settings WHERE name = :settingName', values)
            rs = self.cur.fetchall()

            if len(rs) == 0:
                self.cur.execute('INSERT INTO settings (name, value, last_modified) VALUES (:settingName,:defaultValue,datetime(\'now\'))', values)
                self.con.commit()

    def updateSetting(self, value, settingName):
        self.cur.execute('UPDATE settings SET value = ?, last_modified = datetime(\'now\') WHERE name = ?', (value, settingName))
        self.con.commit()
    
    def getSetting(self, settingName):
        self.cur.execute('SELECT value FROM settings WHERE name = :name', {'name':settingName})
        rs = self.cur.fetchall() 

        return int(rs[0][0]) if rs[0][0].isdigit() else rs[0][0]
    
    def getSettings(self):
        names = []

        for s in self.settingDefaults:
            names.append(s)
        
        sql = 'SELECT name, value FROM settings WHERE name IN ({seq})'.format(seq=','.join(['?']*len(names)))

        self.cur.execute(sql, names)
        res = self.cur.fetchall()

        result = {}
        if len(res) > 0:
            for r in res:
                result[r[0]] = int(r[1]) if r[1].isdigit() else r[1]

        return result

class sun_control_master:
    def __init__(self):
        self.alt = None
        self.azm = None
        
        self.lowerConditions = ['Clear','Mostly Clear']
        self.latitude = 45.466944
        self.longitude = -122.793056

    def get_pos(self, time):
        self.alt = solar.get_altitude(self.latitude, self.longitude, time)
        self.azm = solar.get_azimuth(self.latitude, self.longitude, time)

    def sunInArea(self, sunAzm, sunAlt, startAzm, endAzm, startAlt, endAlt):
        result = False

        if sunAzm > startAzm and sunAzm < endAzm:
            if sunAzm < 180 and sunAlt > startAlt or sunAzm > 180 and sunAlt > endAlt:
                result = True

        return result

    def validateShadeState(self, validateCommand, shade_state):

        if validateCommand == 'confirmRaise':
            if shade_state != '100':
                return 'raiseAll'
                            
        if validateCommand == 'confirmClose':
            if shade_state != '0':
                return 'closeAll'

        return None