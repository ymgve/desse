import base64, cStringIO, logging, random, struct, time, traceback, zlib

from emu.Util import *

class Ghost(object):
    def __init__(self, characterID, ghostBlockID, replayData):
        self.characterID = characterID
        self.ghostBlockID = ghostBlockID
        self.replayData = replayData
        self.timestamp = time.time()

class GhostManager(object):
    def __init__(self):
        self.ghosts = {}
        
    def kill_stale_ghosts(self):
        current_time = time.time()
        
        for ghost in self.ghosts.values():
            if ghost.timestamp + 30.0 <= current_time:
                print "deleted inactive ghost"
                del self.ghosts[ghost.characterID]
    
    def handle_getWanderingGhost(self, params):
        characterID = params["characterID"]
        blockID = make_signed(int(params["blockID"]))
        maxGhostNum = int(params["maxGhostNum"])
        
        self.kill_stale_ghosts()
        
        cands = []
        for ghost in self.ghosts.values():
            if ghost.ghostBlockID == blockID and ghost.characterID != characterID:
                cands.append(ghost)
                
        maxGhostNum = min(maxGhostNum, len(cands))
        
        res = struct.pack("<II", 0, maxGhostNum)
        for ghost in random.sample(cands, maxGhostNum):
            replay = base64.b64encode(ghost.replayData).replace("+", " ")
            res += struct.pack("<I", len(replay))
            res += replay

        return 0x11, res
        
    def handle_setWanderingGhost(self, params):
        characterID = params["characterID"]
        ghostBlockID = make_signed(int(params["ghostBlockID"]))
        replayData = decode_broken_base64(params["replayData"])
        
        # this is not strictly necessary, but it might help weed out bad ghosts that might otherwise crash the game
        if self.validate_replayData(replayData):
            ghost = Ghost(characterID, ghostBlockID, replayData)
            
            if characterID in self.ghosts:
                prevGhostBlockID = self.ghosts[characterID].ghostBlockID
                if ghostBlockID != prevGhostBlockID:
                    logging.debug("Player %r moved from %s to %s" % (characterID, blocknames[prevGhostBlockID], blocknames[ghostBlockID]))
            else:
                logging.debug("Player %r spawned into %s" % (characterID, blocknames[ghostBlockID]))
                
            self.ghosts[characterID] = ghost
        
        return 0x17, "\x01"
    
    def validate_replayData(self, replayData):
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
            logging.warning("bad ghost data %r %r\n%s" % (replayData, data, tb))
            return False

    def get_current_players(self):
        blocks = {}
        total = 0
        
        self.kill_stale_ghosts()
        
        for ghost in self.ghosts.values():
            if ghost.ghostBlockID not in blocks:
                blocks[ghost.ghostBlockID] = 0
            blocks[ghost.ghostBlockID] += 1
            total += 1
                
        blockslist = sorted((v, k) for (k, v) in blocks.items())
        logging.debug("Total players %d %r" % (total, blockslist))
        return total, blockslist
