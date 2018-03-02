import logging, struct, time

from emu.Util import *

class SOSData(object):
    def __init__(self, params, sosID):
        self.sosID = sosID
        self.blockID = make_signed(int(params["blockID"]))
        self.characterID = params["characterID"]
        self.posx = float(params["posx"])
        self.posy = float(params["posy"])
        self.posz = float(params["posz"])
        self.angx = float(params["angx"])
        self.angy = float(params["angy"])
        self.angz = float(params["angz"])
        self.messageID = int(params["messageID"])
        self.mainMsgID = int(params["mainMsgID"])
        self.addMsgCateID = int(params["addMsgCateID"])
        self.playerInfo = params["playerInfo"]
        self.qwcwb = int(params["qwcwb"])
        self.qwclr = int(params["qwclr"])
        self.isBlack = int(params["isBlack"])
        self.playerLevel = int(params["playerLevel"])
        self.ratings = (1, 2, 3, 4, 5) # S, A, B, C, D
        self.totalsessions = 123
        
        self.updatetime = time.time()
        
    def serialize(self):
        res = ""
        res += struct.pack("<I", self.sosID)
        res += self.characterID + "\x00"
        res += struct.pack("<fff", self.posx, self.posy, self.posz)
        res += struct.pack("<fff", self.angx, self.angy, self.angz)
        res += struct.pack("<III", self.messageID, self.mainMsgID, self.addMsgCateID)
        res += struct.pack("<I", 0) # unknown1
        for r in self.ratings:
            res += struct.pack("<I", r)
        res += struct.pack("<I", 0) # unknown2
        res += struct.pack("<I", self.totalsessions)
        res += self.playerInfo + "\x00"
        res += struct.pack("<IIb", self.qwcwb, self.qwclr, self.isBlack)
        
        return res
        
    def __repr__(self):
        if self.isBlack == 1:
            summontype = "Red"
        elif self.isBlack == 2:
            summontype = "Blue"
        elif self.isBlack == 3:
            summontype = "Invasion"
        else:
            summontype = "Unknown (%d)" % self.isBlack
            
        return "<SOS id#%d %s %r %s lv%d>" % (self.sosID, blocknames[self.blockID], self.characterID, summontype, self.playerLevel)

class SOSManager(object):
    def __init__(self):
        self.SOSindex = 1
        self.activeSOS = {}
        self.activeSOS[SERVER_PORT_US] = {}
        self.activeSOS[SERVER_PORT_EU] = {}
        self.activeSOS[SERVER_PORT_JP] = {}
        
        self.monkPending = {}
        self.monkPending[SERVER_PORT_US] = {}
        self.monkPending[SERVER_PORT_EU] = {}
        self.monkPending[SERVER_PORT_JP] = {}
        
        self.playerPending = {}

    def handle_getSosData(self, params, serverport):
        # TODO: limit number of SOS to what the client requests
        
        blockID = make_signed(int(params["blockID"]))
        sosNum = int(params["sosNum"])
        sosList = params["sosList"].split("a0a")
        sos_known = []
        sos_new = []
        
        for sos in self.activeSOS[serverport].values():
            if sos.updatetime + 30 < time.time():
                logging.info("Deleted SOS %r due to inactivity" % sos)
                del self.activeSOS[serverport][sos.characterID]
            else:
                if sos.blockID == blockID:
                    if str(sos.sosID) in sosList:
                        sos_known.append(struct.pack("<I", sos.sosID))
                        logging.debug("adding known SOS %d" % sos.sosID)
                    else:
                        sos_new.append(sos.serialize())
                        logging.debug("adding new SOS %d" % sos.sosID)
    
        data =  struct.pack("<I", len(sos_known)) + "".join(sos_known)
        data += struct.pack("<I", len(sos_new)) + "".join(sos_new)
        
        return 0x0f, data

    def handle_addSosData(self, params, serverport, server):
        sos = SOSData(params, self.SOSindex)
        ratings = server.PlayerManager.getPlayerStats(sos.characterID)
        sos.ratings = ratings[0:5]
        sos.totalsessions = ratings[5]
        
        self.SOSindex += 1
        
        self.activeSOS[serverport][sos.characterID] = sos
        
        logging.info("added SOS, current list %r" % self.activeSOS)
        return 0x0a, "\x01"

    def handle_checkSosData(self, params, serverport):
        characterID = params["characterID"]
        
        if characterID in self.activeSOS[serverport]:
            self.activeSOS[serverport][characterID].updatetime = time.time()
            
        if len(self.playerPending) != 0 or len(self.monkPending[serverport]) != 0:
            logging.debug("Potential connect data %r %r" % (self.playerPending, self.monkPending))
            
        if characterID in self.monkPending[serverport]:
            logging.info("Summoning for monk player %r" % characterID)
            data = self.monkPending[serverport][characterID]
            del self.monkPending[serverport][characterID]
            
        elif characterID in self.playerPending:
            logging.info("Connecting player %r" % characterID)
            data = self.playerPending[characterID]
            del self.playerPending[characterID]
            
        else:
            data = "\x00"
                    
        return 0x0b, data
        
    def handle_summonOtherCharacter(self, params, serverport, playerid):
        ghostID = int(params["ghostID"])
        NPRoomID = params["NPRoomID"]
        logging.info("%r is attempting to summon id#%d" % (playerid, ghostID))
        
        for sos in self.activeSOS[serverport].values():
            if sos.sosID == ghostID:
                logging.info("%r adds pending request for summon %r" % (playerid, sos))
                self.playerPending[sos.characterID] = NPRoomID
                return 0x0a, "\x01"
                
        logging.info("%r failed to summon, id#%d not present" % (playerid, ghostID))
        return 0x0a, "\x00"
            
    def handle_summonBlackGhost(self, params, serverport, playerid):
        NPRoomID = params["NPRoomID"]
        logging.info("%r is attempting to summon for monk" % playerid)
        
        for sos in self.activeSOS[serverport]: 
            if sos.blockID in (40070, 40071, 40072, 40073, 40074, 40170, 40171, 40172, 40270):
                logging.info("%r adds pending request for monk %r" % (playerid, sos))
                self.monkPending[serverport][sos.characterID] = NPRoomID
                return 0x23, "\x01"
                
        logging.info("%r failed to summon for monk" % playerid)
        return 0x23, "\x00"
    
    def handle_outOfBlock(self, params, serverport):
        characterID = params["characterID"]
        if characterID in self.activeSOS[serverport]:
            logging.debug("removing old SOS %r" % characterID)
            del self.activeSOS[serverport][characterID]
            
        return 0x15, "\x01"
