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
            'lastAlt':'null',
            'conditionHistoryLength':5
        }

        self.conditionDefaults = ['Clear','Mostly Clear']
        
        # connect to DB and get ready for queries
        self.con = sqlite3.connect('persist.db')
        self.cur = self.con.cursor()

        self._init_db()

    def _init_db(self):
        self.cur.execute('CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, value TEXT, last_modified TEXT)')
        self.cur.execute('CREATE TABLE IF NOT EXISTS conditionHistory (id INTEGER PRIMARY KEY AUTOINCREMENT, condition TEXT, timestamp TEXT)')
        self.cur.execute('CREATE TABLE IF NOT EXISTS distinctConditions (id INTEGER PRIMARY KEY AUTOINCREMENT, condition TEXT, blindsClosed INTEGER)')

        for s in self.settingDefaults:
            values = {"settingName":s,"defaultValue":self.settingDefaults[s]}

            self.cur.execute('SELECT id FROM settings WHERE name = :settingName', values)
            rs = self.cur.fetchall()

            if len(rs) == 0:
                self.cur.execute('INSERT INTO settings (name, value, last_modified) VALUES (:settingName,:defaultValue,datetime(\'now\'))', values)
                self.con.commit()

        self.cur.execute('SELECT id FROM distinctConditions')
        rs = self.cur.fetchall()

        if len(rs) == 0:
            for c in self.conditionDefaults:
                values = {"condition":c}

                self.cur.execute('INSERT INTO distinctConditions (condition, blindsClosed) VALUES (:condition, 1) ', values)
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

    def logCondition(self, condition):
        self.cur.execute('INSERT INTO conditionHistory (condition, timestamp) VALUES(?, datetime(\'now\'))', (condition,))
        self.con.commit()

        self.cur.execute('SELECT id FROM distinctConditions WHERE condition = ?', (condition,))
        rs = self.cur.fetchall()

        if len(rs) == 0:
            self.cur.execute('INSERT INTO distinctConditions (condition, blindsClosed) VALUES (?, 0)', (condition,))
            self.con.commit()

        self.cur.execute('SELECT value FROM settings WHERE name = \'conditionHistoryLength\'')
        rs = self.cur.fetchall()

        histLengthMax = int(rs[0][0])

        self.cur.execute('SELECT COUNT(*) FROM conditionHistory')
        rs = self.cur.fetchall()

        currentHistLength = int(rs[0][0])

        if (currentHistLength > histLengthMax):
            deleteCount = currentHistLength - histLengthMax

            self.cur.execute('DELETE FROM conditionHistory ORDER BY timestamp ASC LIMIT :count', {'count':deleteCount})
            self.con.commit()
    
    def topConditionFromHistory(self):
        self.cur.execute('SELECT condition, COUNT(*) as histCount FROM conditionHistory GROUP BY condition ORDER BY histCount DESC')
        rs = self.cur.fetchall()

        return rs[0][0]


class sun_control_master:
    def __init__(self):
        self.alt = None
        self.azm = None

        con = sqlite3.connect('persist.db')
        cur = con.cursor()

        cur.execute('SELECT condition FROM distinctConditions WHERE blindsClosed = 1')
        rs = cur.fetchall()

        conditions = []
        for row in rs:
            conditions.append(row[0])
        
        self.lowerConditions = conditions
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