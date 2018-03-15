import cStringIO, logging, os, sqlite3, struct

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

    def from_params(self, params, ghostID, rawReplay):
        self.ghostID = ghostID
        self.characterID = params["characterID"]
        self.blockID = make_signed(int(params["blockID"]))
        self.posx = float(params["posx"])
        self.posy = float(params["posy"])
        self.posz = float(params["posz"])
        self.angx = float(params["angx"])
        self.angy = float(params["angy"])
        self.angz = float(params["angz"])
        self.messageID = int(params["messageID"])
        self.mainMsgID = int(params["mainMsgID"])
        self.addMsgCateID = int(params["addMsgCateID"])
        self.replayBinary = base64.b64encode(rawReplay).replace("+", " ")
        self.legacy = 0

    def from_db_row(self, row):
        self.ghostID, self.characterID, self.blockID, self.posx, self.posy, self.posz, self.angx, self.angy, self.angz, self.messageID, self.mainMsgID, self.addMsgCateID, self.replayBinary, self.legacy = row
        self.characterID = self.characterID.encode("utf8")
        self.replayBinary = self.replayBinary.encode("utf8")

    def to_db_row(self):
        return (self.ghostID, self.characterID, self.blockID, self.posx, self.posy, self.posz, self.angx, self.angy, self.angz, self.messageID, self.mainMsgID, self.addMsgCateID, self.replayBinary, self.legacy)

    def serialize_header(self):
        res = ""
        res += struct.pack("<I", self.ghostID)
        res += self.characterID + "\x00"
        res += struct.pack("<iffffff", self.blockID, self.posx, self.posy, self.posz, self.angx, self.angy, self.angz)
        res += struct.pack("<iii", self.messageID, self.mainMsgID, self.addMsgCateID)
        return res

    def __str__(self):
        return "<Replay: ghostID %d player %r block %s>" % (self.ghostID, self.characterID, blocknames[self.blockID])
        
class ReplayManager(object):
    def __init__(self):
        dbfilename = "db/replays.sqlite"
        if not os.path.isfile(dbfilename):
            conn = sqlite3.connect(dbfilename)
            c = conn.cursor()
            c.execute("""create table replays(
                ghostID integer primary key autoincrement,
                characterID text,
                blockID integer,
                posx real,
                posy real,
                posz real,
                angx real,
                angy real,
                angz real,
                messageID integer,
                mainMsgID integer,
                addMsgCateID integer,
                replayBinary text,
                legacy integer)""")
            
            f = open("data/legacyreplaydata.bin", "rb")
            while True:
                data = f.read(4)
                if len(data) == 0:
                    break
                sz = struct.unpack("<I", data)[0]
                
                rep = Replay()
                rep.unserialize(f.read(sz))
                        
                c.execute("insert into replays(ghostID, characterID, blockID, posx, posy, posz, angx, angy, angz, messageID, mainMsgID, addMsgCateId, replayBinary, legacy) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rep.to_db_row())
                
            conn.commit()
            conn.close()
            
            logging.info("Loaded legacy replays into database")
        
        self.conn = sqlite3.connect(dbfilename)
        
    def handle_getReplayList(self, params):
        blockID = make_signed(int(params["blockID"]))
        replayNum = int(params["replayNum"])

        to_send = []
        
        # first non-legacy replays
        remaining = replayNum
        num_live = 0
        for row in self.conn.execute("select * from replays where blockID = ? and legacy = 0 order by random() limit ?", (blockID, remaining)):
            rep = Replay()
            rep.from_db_row(row)
            to_send.append(rep.serialize_header())
            num_live += 1
        
        # then legacy replays
        remaining = replayNum - len(to_send)
        num_legacy = 0
        if num_live < LEGACY_REPLAY_THRESHOLD and remaining > 0:
            for row in self.conn.execute("select * from replays where blockID = ? and legacy = 1 order by random() limit ?", (blockID, remaining)):
                rep = Replay()
                rep.from_db_row(row)
                to_send.append(rep.serialize_header())
                num_legacy += 1

        res = struct.pack("<I", len(to_send)) + "".join(to_send)

        logging.debug("Sending %d live replays and %d legacy replays for block %s" % (num_live, num_legacy, blocknames[blockID]))
        
        return 0x1f, res
        
    def handle_addReplayData(self, params):
        rawReplay = decode_broken_base64(params["replayBinary"])
        
        if validate_replayData(rawReplay):
            rep = Replay()
            rep.from_params(params, None, rawReplay)
        
            c = self.conn.cursor()
            c.execute("insert into replays(characterID, blockID, posx, posy, posz, angx, angy, angz, messageID, mainMsgID, addMsgCateId, replayBinary, legacy) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rep.to_db_row()[1:])
            rep.ghostID = c.lastrowid
            self.conn.commit()
            
            custom_command = None
            logging.info("Added new replay %s" % str(rep))

        return 0x1d, "\x01"
        
    def handle_getReplayData(self, params):
        ghostID = int(params["ghostID"])
        
        row = self.conn.execute("select * from replays where ghostID = ?", (ghostID,)).fetchone()
        if row is None:
            logging.warning("Tried to read replayID %d data which does not exist" % ghostID)
            replayBinary = ""
        else:
            rep = Replay()
            rep.from_db_row(row)
            logging.info("Player requested info for replay %s" % rep)
            replayBinary = rep.replayBinary
        
        res = struct.pack("<II", ghostID, len(replayBinary)) + replayBinary
            
        return 0x1e, res
