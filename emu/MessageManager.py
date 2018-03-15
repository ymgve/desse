import cStringIO, logging, os, sqlite3, struct

from emu.Util import *

class Message(object):
    def __init__(self):
        pass
        
    def unserialize(self, data):
        sio = cStringIO.StringIO(data)
        self.bmID = struct.unpack("<I", sio.read(4))[0]
        self.characterID = readcstring(sio)
        self.blockID, self.posx, self.posy, self.posz, self.angx, self.angy, self.angz = struct.unpack("<iffffff", sio.read(28))
        self.messageID, self.mainMsgID, self.addMsgCateID, self.rating = struct.unpack("<iiii", sio.read(16))
        assert sio.read() == ""
        self.legacy = 1
        
    def from_params(self, params, bmID):
        self.bmID = bmID
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
        self.rating = 0
        self.legacy = 0

    def from_db_row(self, row):
        self.bmID, self.characterID, self.blockID, self.posx, self.posy, self.posz, self.angx, self.angy, self.angz, self.messageID, self.mainMsgID, self.addMsgCateID, self.rating, self.legacy = row
        self.characterID = self.characterID.encode("utf8")
        
    def to_db_row(self):
        return (self.bmID, self.characterID, self.blockID, self.posx, self.posy, self.posz, self.angx, self.angy, self.angz, self.messageID, self.mainMsgID, self.addMsgCateID, self.rating, self.legacy)
        
    def serialize(self):
        res = ""
        res += struct.pack("<I", self.bmID)
        res += self.characterID + "\x00"
        res += struct.pack("<iffffff", self.blockID, self.posx, self.posy, self.posz, self.angx, self.angy, self.angz)
        res += struct.pack("<iiii", self.messageID, self.mainMsgID, self.addMsgCateID, self.rating)
        return res

    def __str__(self):
        if self.mainMsgID in messageids:
            if self.messageID in messageids:
                extra = messageids[self.messageID]
            else:
                extra = "[%d]" % self.messageID
                
            message = messageids[self.mainMsgID].replace("***", extra)
            prettymessage = "%d %s %r %s %d" % (self.bmID, blocknames[self.blockID], self.characterID, message, self.rating)
            
        else:
            prettymessage = "%d %s %r [%d] [%d] %d" % (self.bmID, blocknames[self.blockID], self.characterID, self.messageID, self.mainMsgID, self.rating)

        return prettymessage
        
class MessageManager(object):
    def __init__(self):
        dbfilename = "db/messages.sqlite"
        if not os.path.isfile(dbfilename):
            conn = sqlite3.connect(dbfilename)
            c = conn.cursor()
            c.execute("""create table messages(
                bmID integer primary key autoincrement,
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
                rating integer,
                legacy integer)""")
            
            f = open("data/legacymessagedata.bin", "rb")
            while True:
                data = f.read(4)
                if len(data) == 0:
                    break
                sz = struct.unpack("<I", data)[0]
                
                msg = Message()
                msg.unserialize(f.read(sz))
                        
                c.execute("insert into messages(bmID, characterID, blockID, posx, posy, posz, angx, angy, angz, messageID, mainMsgID, addMsgCateId, rating, legacy) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", msg.to_db_row())
                
            conn.commit()
            conn.close()
            
            logging.info("Loaded legacy messages into database")
        
        self.conn = sqlite3.connect(dbfilename)
        
    def handle_getBloodMessage(self, params):
        characterID = params["characterID"]
        blockID = make_signed(int(params["blockID"]))
        replayNum = int(params["replayNum"])
        
        to_send = []
        
        # first own non-legacy messages
        remaining = replayNum
        num_own = 0
        for row in self.conn.execute("select * from messages where characterID = ? and blockID = ? and legacy = 0 order by random() limit ?", (characterID, blockID, remaining)):
            msg = Message()
            msg.from_db_row(row)
            to_send.append(msg.serialize())
            num_own += 1
            
        # then others non-legacy messages
        remaining = replayNum - len(to_send)
        num_others = 0
        if remaining > 0:
            for row in self.conn.execute("select * from messages where characterID != ? and blockID = ? and legacy = 0 order by random() limit ?", (characterID, blockID, remaining)):
                msg = Message()
                msg.from_db_row(row)
                to_send.append(msg.serialize())
                num_others += 1
            
        # then legacy messages
        remaining = replayNum - len(to_send)
        num_legacy = 0
        if (num_own + num_others) < LEGACY_MESSAGE_THRESHOLD and remaining > 0:
            for row in self.conn.execute("select * from messages where blockID = ? and legacy = 1 order by random() limit ?", (blockID, remaining)):
                msg = Message()
                msg.from_db_row(row)
                to_send.append(msg.serialize())
                num_legacy += 1
        
        res = struct.pack("<I", len(to_send)) + "".join(to_send)
            
        logging.debug("Sending %d own messages, %d others messages and %d legacy messages for block %s" % (num_own, num_others, num_legacy, blocknames[blockID]))
        
        return 0x1f, res
        
    def handle_addBloodMessage(self, params):
        msg = Message()
        msg.from_params(params, None)
        
        if msg.mainMsgID == 13002:
            custom_command = (msg.messageID - 40700) * 10
            logging.info("Player %s triggered custom command %d" % (msg.characterID, custom_command))
        else:
            c = self.conn.cursor()
            c.execute("insert into messages(characterID, blockID, posx, posy, posz, angx, angy, angz, messageID, mainMsgID, addMsgCateId, rating, legacy) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", msg.to_db_row()[1:])
            msg.bmID = c.lastrowid
            self.conn.commit()
            
            custom_command = None
            logging.info("Added new message %s" % str(msg))
            
        return 0x1d, "\x01", custom_command
        
    def handle_deleteBloodMessage(self, params):
        bmID = int(params["bmID"])
        
        row = self.conn.execute("select * from messages where bmID = ?", (bmID,)).fetchone()
        msg = Message()
        msg.from_db_row(row)
        
        self.conn.execute("delete from messages where bmID = ?", (bmID,))
        self.conn.commit()
        
        logging.info("Deleted message %s" % str(msg))
        
        return 0x27, "\x01"
        
    def handle_updateBloodMessageGrade(self, params, server):
        bmID = int(params["bmID"])
        
        self.conn.execute("update messages set rating = rating + 1 where bmID = ?", (bmID,))
        self.conn.commit()
        
        row = self.conn.execute("select * from messages where bmID = ?", (bmID,)).fetchone()
        msg = Message()
        msg.from_db_row(row)
        
        server.PlayerManager.updateBloodMessageGrade(msg.characterID)
        
        logging.info("Recommended message %s" % str(msg))
        
        return 0x2a, "\x01"
