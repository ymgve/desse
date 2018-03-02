import logging, os, sqlite3, struct

from emu.Util import *

class PlayerManager(object):
    def __init__(self):
        dbfilename = "db/players.sqlite"
        if not os.path.isfile(dbfilename):
            conn = sqlite3.connect(dbfilename)
            c = conn.cursor()
            c.execute("""create table players(
                characterID text primary key,
                gradeS integer,
                gradeA integer,
                gradeB integer,
                gradeC integer,
                gradeD integer,
                numsessions integer,
                messagerating integer,
                desired_tendency integer)""")
                
            conn.commit()
            conn.close()
            
            logging.info("Created user database")
            
        self.conn = sqlite3.connect(dbfilename)

    def ensure_user_created(self, characterID):
        row = self.conn.execute("select count(*) from players where characterID = ?", (characterID,)).fetchone()
        if row[0] == 0:
            self.conn.execute("insert into players(characterID, gradeS, gradeA, gradeB, gradeC, gradeD, numsessions, messagerating, desired_tendency) VALUES (?,?,?,?,?,?,?,?,?)", (characterID, 5, 4, 3, 2, 1, 123, 0, 0))
            self.conn.commit()
            logging.info("Created new player %r in database" % characterID)
    
    def handle_initializeCharacter(self, params):
        characterID = params["characterID"]
        index = params["index"]
        characterID = characterID + index[0]
        
        self.ensure_user_created(characterID)
        logging.info("Player %r logged in" % characterID)
        
        data = characterID + "\x00"
        return 0x17, data, characterID
        
    def handle_getQWCData(self, params, characterID):
        self.ensure_user_created(characterID)
        
        row = self.conn.execute("select desired_tendency from players where characterID = ?", (characterID,)).fetchone()
        desired_tendency = row[0]
        
        data = ""
        for i in xrange(7):
            data += struct.pack("<ii", desired_tendency, 0)
            
        return 0x0e, data
    
    def handle_getMultiPlayGrade(self, params):
        characterID = params["NPID"]
        ratings = self.getPlayerStats(characterID)
        data = "\x01" + struct.pack("<iiiiii", *ratings)
        return 0x28, data
        
    def handle_getBloodMessageGrade(self, params):
        characterID = params["NPID"]
        row = self.conn.execute("select messagerating from players where characterID = ?", (characterID,)).fetchone()
        messagerating = row[0]
        data = "\x01" + struct.pack("<i", messagerating)
        return 0x29, data
    
    def handle_finalizeMultiPlay(self, params):
        # TODO - the characterID is of your own player, need some way to direct the grading to the right user
        # there's a "presence" parameter that seems to match between players, might use that
        
        characterID = params["characterID"]
        self.ensure_user_created(characterID)
        
        gradetext = "??no grade??"
        for key in ("gradeS", "gradeA", "gradeB", "gradeC", "gradeD"):
            if params[key] == "1":
                # self.conn.execute("update players set %s = %s + 1 where characterID = ?" % key, (characterID,))
                # self.conn.commit()
                gradetext == key
                break

        logging.info("Player %r finished a multiplayer session successfully and gave %s" % (characterID, gradetext))
        
        return 0x21, "\x01"
        
    def handle_updateOtherPlayerGrade(self, params, myCharacterID):
        characterID = params["characterID"]
        
        key = ("gradeS", "gradeA", "gradeB", "gradeC", "gradeD")[int(params["grade"])]
        self.conn.execute("update players set %s = %s + 1 where characterID = ?" % key, (characterID,))
        self.conn.commit()
        logging.info("Player %r gave player %r a %s rating" % (myCharacterID, characterID, gradetext))
        
        return 0x2b, "\x01"
    
    def getPlayerStats(self, characterID):
        self.ensure_user_created(characterID)
        return self.conn.execute("select gradeS, gradeA, gradeB, gradeC, gradeD, numsessions from players where characterID = ?", (characterID,)).fetchone()
        
    def updateBloodMessageGrade(self, characterID):
        c = self.conn.cursor()
        c.execute("update players set messagerating = messagerating + 1 where characterID = ?", (characterID,)).fetchone()
        self.conn.commit()
        logging.info("Updated blood message grade for player %r, rows affected %d" % (characterID, c.rowcount))

