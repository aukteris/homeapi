import sqlite3

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
            'luxThresh':3000,
            'conditionHistoryLength':5,
            'commandOverride':0,
            'solarThresh':20,
            'changeBufferDurationSec':600,
            'lastChangeDate':0,
            'upperAlt':55,
            'lowerAlt':15,
            'upperAltPer':1,
            'lowerAltPer':0.5,
            'ticktockInterval':30
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
        
        self.cur.execute('SELECT id FROM conditionHistory')
        rs = self.cur.fetchall()

        if len(rs) == 0:
            condition = 'Clear'
            self.cur.execute('INSERT INTO conditionHistory (condition, timestamp) VALUES(?, datetime(\'now\'))', (condition,))
            self.con.commit()
    
    def disconnect(self):
        self.con.close()

    def updateSetting(self, value, settingName):
        self.cur.execute('UPDATE settings SET value = ?, last_modified = datetime(\'now\') WHERE name = ?', (value, settingName))
        self.con.commit()
    
    def getSetting(self, settingName):
        self.cur.execute('SELECT value FROM settings WHERE name = :name', {'name':settingName})
        rs = self.cur.fetchall() 

        return int(rs[0][0]) if rs[0][0].isdigit() else float(rs[0][0]) if self.is_float(rs[0][0]) else rs[0][0]
    
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
                result[r[0]] = int(r[1]) if r[1].isdigit() else float(r[1]) if self.is_float(r[1]) else r[1]

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

    def topConditionTypeFromHistory(self):
        self.cur.execute('SELECT blindsClosed, COUNT(timestamp) AS histCount FROM conditionHistory INNER JOIN distinctConditions ON conditionHistory.condition = distinctConditions.condition GROUP BY blindsClosed ORDER BY histCount DESC')
        rs = self.cur.fetchall()

        retval = "close" if rs[0][0] == 1 else "open"

        return retval
    
    def is_float(self, string):
        try:
            float(string)
            return True
        except ValueError:
            return False
