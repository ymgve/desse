import base64, struct

from Crypto.Cipher import AES

def make_signed(n):
    if n >= (1 << 31):
        return n - (1 << 32)
    else:
        return n
        
def decrypt(ct):
    a = AES.new("11111111222222223333333344444444", AES.MODE_CBC, ct[0:16])
    pt = a.decrypt(ct[16:])
    pt = pt[:-ord(pt[-1])]
    
    return pt

def get_params(data):
    params = {}
    for param in data.split("&"):
        if param == "\x00" or param == "":
            continue
            
        if "=" in param:
            key, value = param.split("=", 1)
            params[key] = value
            
    return params
        
def decode_broken_base64(data):
    s = ""
    for c in data:
        if c in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz/+":
            s += c
        else:
            if c == " ":
                s += "+"
            else:
                break
    
    if len(s) % 4 == 3:
        s += "="
    elif len(s) % 4 == 2:
        s += "=="
    elif len(s) % 4 == 1:
        s += "A=="

    return base64.b64decode(s)

def readcstring(sio):
    res = ""
    while True:
        c = sio.read(1)
        assert len(c) == 1
        if c == "\x00":
            break
            
        res += c
    return res

class ReplayHeader(object):
    def __init__(self):
        pass
        
    def create(self, sio):
        ghostID = sio.read(4)
        if len(ghostID) != 4:
            return False
            
        self.ghostID = struct.unpack("<I", ghostID)[0]
        
        self.name = readcstring(sio)
        self.data = sio.read(40)
        
        self.blockID, self.posx, self.posy, self.posz, self.angx, self.angy, self.angz, self.messageID, self.mainMsgID, self.addMsgCateID = struct.unpack("<iffffffIII", self.data)
        
        return True
        
    def to_bin(self):
        res = struct.pack("<I", self.ghostID)
        res += self.name + "\x00"
        res += self.data
        return res