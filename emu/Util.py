import base64, traceback, logging, zlib, cStringIO, struct

from Crypto.Cipher import AES

SERVER_PORT_BOOTSTRAP = 18000
SERVER_PORT_US = 18666
SERVER_PORT_EU = 18667
SERVER_PORT_JP = 18668

LEGACY_MESSAGE_THRESHOLD = 5
LEGACY_REPLAY_THRESHOLD = 5

blocknames = {}
for line in open("data/blocknames.txt", "rb"):
    blockID, blockname = line.strip().split("|")
    blocknames[int(blockID)] = blockname

messageids = {}
for line in open("data/messageids.txt", "rb"):
    id, text = line.strip().split("|", 1)
    messageids[int(id)] = text

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

def validate_replayData(replayData):
    try:
        z = zlib.decompressobj()
        data = z.decompress(replayData)
        assert z.unconsumed_tail == ""
        
        sio = cStringIO.StringIO(data)
        
        poscount, num1, num2 = struct.unpack(">III", sio.read(12))
        for i in xrange(poscount):
            posx, posy, posz, angx, angy, angz, num3, num4 = struct.unpack(">ffffffII", sio.read(32))
            
        unknowns = struct.unpack(">iiiiiiiiiiiiiiiiiiii", sio.read(4 * 20))
        playername = sio.read(34).decode("utf-16be").rstrip("\x00")
        assert sio.read() == ""
        
        return True
        
    except:
        tb = traceback.format_exc()
        logging.warning("bad ghost/replay data %r %r\n%s" % (replayData, data, tb))
        return False
