import cStringIO, logging, os, sqlite3, struct, random

from emu.Util import *

class Replay(object):
    def __init__(self):
        pass
        
    def unserialize(self, data):
        sio = cStringIO.StringIO(data)
        self.ghostID = struct.unpack("<I", sio.read(4))[0]
        self.characterID = readcstring(sio)
        self.blockID, self.posx, self.posy, self.posz, self.angx, self.angy, self.angz = struct.unpack("<iffffff", sio.read(28))
        self.messageID, self.mainMsgID, self.addMsgCateID = struct.unpack("<iii", sio.read(12))
        self.replayBinary = readcstring(sio)
        assert sio.read() == ""
        self.legacy = 1

    def serialize_header(self):
        res = ""
        res += struct.pack("<I", self.ghostID)
        res += self.characterID + "\x00"
        res += struct.pack("<iffffff", self.blockID, self.posx, self.posy, self.posz, self.angx, self.angy, self.angz)
        res += struct.pack("<iii", self.messageID, self.mainMsgID, self.addMsgCateID)
        return res

class ReplayManager(object):
    def __init__(self):
        self.replays = {}
        
        f = open("data/legacyreplaydata.bin", "rb")
        while True:
            data = f.read(4)
            if len(data) == 0:
                break
            sz = struct.unpack("<I", data)[0]
            
            rep = Replay()
            rep.unserialize(f.read(sz))
                    
            self.replays[rep.ghostID] = rep
            
        logging.info("Finished reading replay data")
        
    def handle_getReplayList(self, params):
        blockID = make_signed(int(params["blockID"]))
        replayNum = int(params["replayNum"])

        data = struct.pack("<I", replayNum)
        while replayNum > 0:
            rep = random.choice(self.replays.values())
            if blockID == rep.blockID:
                data += rep.serialize_header()
                replayNum -= 1

        return 0x1f, data
        
    def handle_getReplayData(self, params):
        ghostID = int(params["ghostID"])
        
        replayBinary = self.replays[ghostID].replayBinary
        data = struct.pack("<II", ghostID, len(replayBinary)) + replayBinary
            
        return 0x1e, data
