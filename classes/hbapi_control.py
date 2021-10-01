class hb_authorize:
    def __init__(self, host=None, port=None, user=None, passwd=None, config=None):
        self.host = host
        self.port = port
        self.username = user
        self.password = passwd
        self.configFile = config

class set_acc_char_data:
    def __init__(self, name, chars, session):
        self.name = name
        self.charSet = chars
        self.sessionId = session