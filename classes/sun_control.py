from pysolar import solar

class sun_control_master:
    def __init__(self, db_session):
        self.alt = None
        self.azm = None

        db_session.cur.execute('SELECT condition FROM distinctConditions WHERE blindsClosed = 1')
        rs = db_session.cur.fetchall()

        conditions = []
        for row in rs:
            conditions.append(row[0])
        
        # TODO: need to make long and lat configurable
        self.lowerConditions = conditions
        self.latitude = 45.46692
        self.longitude = -122.79286

    def get_pos(self, time):
        self.alt = solar.get_altitude(self.latitude, self.longitude, time)
        self.azm = solar.get_azimuth(self.latitude, self.longitude, time)

    def sunInArea(self, sunAzm, sunAlt, startAzm, endAzm, startAlt, endAlt):
        result = False

        if sunAzm > float(startAzm) and sunAzm < float(endAzm):
            if sunAzm < 180 and sunAlt > float(startAlt) or sunAzm > 180 and sunAlt > float(endAlt):
                result = True

        return result

    def validateShadeState(self, validateCommand, shade_state):
        conditionArgs = {
            'confirmRaise': {
                'targetState': 100,
                'command': 'raiseAll'
            },
            'confirmClose': {
                'targetState': 0,
                'command': 'closeAll'
            }
        }

        for state in shade_state.values():
            if (state != conditionArgs[validateCommand]['targetState']):
                return conditionArgs[validateCommand]['command']

        return None