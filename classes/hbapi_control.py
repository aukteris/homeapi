class hb_authorize:
    def __init__(self, host=None, port=None, user=None, passwd=None, config=None, secure=False):
        self.host = host
        self.port = port
        self.username = user
        self.password = passwd
        self.configFile = config
        self.secure = secure

class acc_char_data:
    def __init__(self, name=None, chars=None, session=None):
        self.name = name
        self.charSet = chars
        self.sessionId = session