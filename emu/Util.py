import base64

from Crypto.Cipher import AES

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
