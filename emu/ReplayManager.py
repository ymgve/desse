import cStringIO, logging, os, sqlite3, struct, random

from emu.Util import *

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
        
class ReplayManager(object):
    def __init__(self):
        self.replayheaders = {}
        self.replaydata = {}
        
        f = open("replayheaders.bin", "rb")
        while True:
            header = ReplayHeader()
            res = header.create(f)
            if not res:
                break
                
            if header.blockID not in self.replayheaders:
                self.replayheaders[header.blockID] = []
                
            if (header.messageID, header.mainMsgID, header.addMsgCateID) != (0, 0, 0):
                self.replayheaders[header.blockID].append(header)
                
        logging.info("Finished reading replay headers")
        
        f = open("replaydata.bin", "rb")
        while True:
            ghostID = f.read(4)
            if len(ghostID) != 4:
                break
            ghostID = struct.unpack("<I", ghostID)[0]
            
            data = readcstring(f)
            
            self.replaydata[ghostID] = data
            
        logging.info("Finished reading replay data")
        
    def handle_getReplayList(self, params):
        blockID = make_signed(int(params["blockID"]))
        replayNum = int(params["replayNum"])
        
        data = struct.pack("<I", replayNum)
        for i in xrange(replayNum):
            header = random.choice(self.replayheaders[blockID])
            data += header.to_bin()
            
        return 0x1f, data
        
    def handle_getReplayData(self, params):
        ghostID = int(params["ghostID"])
        
        ghostdata = self.replaydata[ghostID]
        data = struct.pack("<II", ghostID, len(ghostdata)) + ghostdata
            
        return 0x1e, data
