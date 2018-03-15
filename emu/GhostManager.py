import base64, cStringIO, logging, random, struct, time

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
                logging.debug("Deleted inactive ghost of %r" % ghost.characterID)
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
        
    def handle_setWanderingGhost(self, params, serverport):
        characterID = params["characterID"]
        ghostBlockID = make_signed(int(params["ghostBlockID"]))
        replayData = decode_broken_base64(params["replayData"])
        
        # this is not strictly necessary, but it might help weed out bad ghosts that might otherwise crash the game
        if validate_replayData(replayData):
            ghost = Ghost(characterID, ghostBlockID, replayData)
            
            if characterID in self.ghosts:
                prevGhostBlockID = self.ghosts[characterID].ghostBlockID
                if ghostBlockID != prevGhostBlockID:
                    logging.debug("Player %r moved from %s to %s" % (characterID, blocknames[prevGhostBlockID], blocknames[ghostBlockID]))
            else:
                logging.debug("Player %r spawned into %s" % (characterID, blocknames[ghostBlockID]))
                
            self.ghosts[characterID] = ghost
            self.ghosts[characterID].serverport = serverport
        
        return 0x17, "\x01"
    
    def get_current_players(self, serverport):
        blocks = {}
        regiontotal = {}
        regiontotal[SERVER_PORT_US] = 0
        regiontotal[SERVER_PORT_EU] = 0
        regiontotal[SERVER_PORT_JP] = 0
        
        self.kill_stale_ghosts()
        
        for ghost in self.ghosts.values():
            regiontotal[ghost.serverport] += 1
            
            if ghost.serverport == serverport:
                if ghost.ghostBlockID not in blocks:
                    blocks[ghost.ghostBlockID] = 0
                blocks[ghost.ghostBlockID] += 1
                
        blockslist = sorted((v, k) for (k, v) in blocks.items())
        logging.debug("Total players %r %r" % (regiontotal, blockslist))
        return regiontotal, blockslist
