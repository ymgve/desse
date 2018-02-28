import socket, traceback, struct, base64, random, cStringIO, zlib, select
from time import gmtime, strftime

from helpers import *

SERVER_PORT_BOOTSTRAP = 18000
SERVER_PORT_US = 18666
SERVER_PORT_EU = 18667
SERVER_PORT_JP = 18668

blocknames = {}
for line in open("blocknames.txt", "rb"):
    blockID, blockname = line.strip().split("|")
    blocknames[int(blockID)] = blockname
    
class ImpSock(object):
    def __init__(self, sc, name):
        self.sc = sc
        self.name = name
        self.recvdata = ""
        
    def recv(self, sz):
        data = self.sc.recv(sz)
        self.recvdata += data
        return data
    
    def close(self):
        self.sc.close()
        
    def sendall(self, data):
        self.sc.sendall(data)
        
    def recv_line(self):
        line = ""
        while True:
            c = self.recv(1)
            if len(c) == 0:
                print "DISCONNECT at line", repr(line)
                raise Exception("DISCONNECT")
            line += c
            if line.endswith("\r\n"):
                line = line[:-2]
                #print self.name, "received", repr(line)
                # debugwrite(self.name, repr(line))
                return line
            
    def recv_all(self, size):
        res = ""
        while len(res) < size:
            data = self.recv(size - len(res))
            if len(data) == 0:
                print "DISCONNECT", repr(res)
                raise Exception("DISCONNECT")
            res += data
            
        #print self.name, "received", repr(res)
        # debugwrite(self.name, repr(res))
        return res
            
    def recv_headers(self):
        headers = {}
        while True:
            line = self.recv_line()
            if len(line) == 0:
                break
            key, value = line.split(": ")
            headers[key] = value
            
        return headers
    
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
        self.Xratings = (1, 2, 3, 4, 5) # S, A, B, C, D
        self.Xtotalsessions = 123
        
    def serialize(self):
        res = ""
        res += struct.pack("<I", self.sosID)
        res += self.characterID + "\x00"
        res += struct.pack("<fff", self.posx, self.posy, self.posz)
        res += struct.pack("<fff", self.angx, self.angy, self.angz)
        res += struct.pack("<III", self.messageID, self.mainMsgID, self.addMsgCateID)
        res += struct.pack("<I", 0) # unknown1
        for r in self.Xratings:
            res += struct.pack("<I", r)
        res += struct.pack("<I", 0) # unknown2
        res += struct.pack("<I", self.Xtotalsessions)
        res += self.playerInfo + "\x00"
        res += struct.pack("<IIb", self.qwcwb, self.qwclr, self.isBlack)
        
        return res

class SOSManager(object):
    def __init__(self):
        self.SOSindex = 1
        self.activeSOS = {}
        self.activeSOS[SERVER_PORT_US] = {}
        self.activeSOS[SERVER_PORT_EU] = {}
        self.activeSOS[SERVER_PORT_JP] = {}
        
        self.playerPending = {}

    def handle_getSosData(self, params, serverport):
        # TODO: limit number of SOS to what the client requests
        
        blockID = make_signed(int(params["blockID"]))
        sosNum = int(params["sosNum"])
        sosList = params["sosList"].split("a0a")
        sos_known = []
        sos_new = []
        
        for sos in self.activeSOS[serverport].values():
            if sos.blockID == blockID:
                if str(sos.sosID) in sosList:
                    sos_known.append(struct.pack("<I", sos.sosID))
                    print "adding known SOS", sos.sosID
                else:
                    sos_new.append(sos.serialize())
                    print "adding new SOS", sos.sosID
    
        data =  struct.pack("<I", len(sos_known)) + "".join(sos_known)
        data += struct.pack("<I", len(sos_new)) + "".join(sos_new)
        print "sending", repr(data)
        
        return 0x0f, data

    def handle_addSosData(self, params, serverport):
        sos = SOSData(params, self.SOSindex)
        self.SOSindex += 1
        
        self.activeSOS[serverport][sos.characterID] = sos
        
        print "added SOS, current list", self.activeSOS
        return 0x0a, "\x01"

    def handle_checkSosData(self, params, serverport):
        characterID = params["characterID"]
        
        print characterID, self.playerPending
        if characterID in self.playerPending:
            print "GOT DATA, SENDING"
            data = self.playerPending[characterID]
            del self.playerPending[characterID]
        else:
            print "no data"
            data = "\x00"
                    
        return 0x0b, data
        
    def handle_summonOtherCharacter(self, params, serverport):
        ghostID = int(params["ghostID"])
        NPRoomID = params["NPRoomID"]
        print "ghostID", ghostID, repr(NPRoomID), self.activeSOS
        
        for sos in self.activeSOS[serverport].values():
            if sos.sosID == ghostID:
                print "adding to", repr(sos.characterID)
                self.playerPending[sos.characterID] = NPRoomID
                break
        
        return 0x0a, "\x01"
            
    def handle_outOfBlock(self, params, serverport):
        characterID = params["characterID"]
        if characterID in self.activeSOS[serverport]:
            print "removing old SOS"
            del self.activeSOS[serverport][characterID]
            
        return 0x15, "\x01"

class Ghost(object):
    def __init__(self, characterID, ghostBlockID, replayData):
        self.characterID = characterID
        self.ghostBlockID = ghostBlockID
        self.replayData = replayData
        
class GhostManager(object):
    def __init__(self):
        self.ghosts = {}
        
    def handle_getWanderingGhost(self, params):
        characterID = params["characterID"]
        blockID = make_signed(int(params["blockID"]))
        maxGhostNum = int(params["maxGhostNum"])
        
        cands = []
        for ghost in self.ghosts.values():
            if ghost.ghostBlockID == blockID:
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
        posx = float(params["posx"])
        posy = float(params["posy"])
        posz = float(params["posz"])
        replayData = decode_broken_base64(params["replayData"])
        
        try:
            z = zlib.decompressobj()
            data = z.decompress(replayData)
            assert z.unconsumed_tail == ""
            
            sio = cStringIO.StringIO(data)
            poscount, num1, num2 = struct.unpack(">III", sio.read(12))
            #print "%08x %08x %08x" % (poscount, num1, num2)
            for i in xrange(poscount):
                posx, posy, posz, angx, angy, angz, num3, num4 = struct.unpack(">ffffffII", sio.read(32))
                #print "%7.2f %7.2f %7.2f %7.2f %7.2f %7.2f %08x %08x" % (posx, posy, posz, angx, angy, angz, num3, num4)
            unknowns = struct.unpack(">iiiiiiiiiiiiiiiiiiii", sio.read(4 * 20))
            #print unknowns
            playername = sio.read(24).decode("utf-16be").rstrip("\x00")
            #print repr(playername)
            
            ghost = Ghost(characterID, ghostBlockID, replayData)
            self.ghosts[characterID] = ghost
        except:
            print "bad data", repr(params)
            traceback.print_exc()
        
        return 0x17, "\x01"
    
class Server(object):
    def __init__(self):
        self.GhostManager = GhostManager()
        self.SOSManager = SOSManager()
        
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
                
        print "finished read replay headers"
        
        f = open("replaydata.bin", "rb")
        while True:
            ghostID = f.read(4)
            if len(ghostID) != 4:
                break
            ghostID = struct.unpack("<I", ghostID)[0]
            
            data = readcstring(f)
            
            self.replaydata[ghostID] = data
            
        print "finished read replay data"
                
    def run(self):
        servers = []
        for port in (SERVER_PORT_BOOTSTRAP, SERVER_PORT_US, SERVER_PORT_EU, SERVER_PORT_JP):
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(('', port))
            server.listen(5)
            servers.append(server)
        
        print "listening"

        while True:
            try:
                readable, _, _ = select.select(servers, [], [])
                ready_server = readable[0]
                serverport = ready_server.getsockname()[1]
                
                client_sock, client_addr = ready_server.accept()
                sc = ImpSock(client_sock, "client")
                
                req = sc.recv_line()
                print "got connect from", client_addr, "to", serverport, "request", repr(req)
                
                clientheaders = sc.recv_headers()
                        
                cdata = sc.recv_all(int(clientheaders["Content-Length"]))
                cdata = decrypt(cdata)
                
                if serverport == SERVER_PORT_BOOTSTRAP:
                    data = open("info.ss", "rb").read()
                    
                    res = self.prepare_response_bootstrap(data)
                else:
                    params = get_params(cdata)
                    data = None
                    
                    if "login.spd" in req:
                        cmd, data = self.handle_login(cdata)
                        
                    if "initializeCharacter.spd" in req:
                        cmd, data = self.handle_charinit(cdata)
                        
                    if "getQWCData.spd" in req:
                        cmd, data = self.handle_qwcdata(cdata)
                        
                    if "getMultiPlayGrade.spd" in req:
                        cmd = 0x28
                        data = "0100000000000000000000000000000000000000000000000000000000".decode("hex")
                    
                    if "getBloodMessageGrade.spd" in req:
                        cmd = 0x29
                        data = "0100000000".decode("hex")
                        
                    if "getTimeMessage.spd" in req:
                        cmd = 0x22
                        data = "000000".decode("hex")
                    
                    if "getBloodMessage.spd" in req:
                        cmd = 0x1f
                        data = "00000000".decode("hex")
                        
                    if "addReplayData.spd" in req:
                        cmd = 0x1d
                        data = "01000000".decode("hex")
                        
                    if "getReplayList.spd" in req:
                        cmd, data = self.handle_getReplayList(cdata)
                    
                    if "getReplayData.spd" in req:
                        cmd, data = self.handle_getReplayData(cdata)
                    
                    if "getWanderingGhost.spd" in req:
                        cmd, data = self.GhostManager.handle_getWanderingGhost(params)
                        
                    if "setWanderingGhost.spd" in req:
                        cmd, data = self.GhostManager.handle_setWanderingGhost(params)
                        
                    if "getSosData.spd" in req:
                        cmd, data = self.SOSManager.handle_getSosData(params, serverport)
                        
                    if "addSosData.spd" in req:
                        cmd, data = self.SOSManager.handle_addSosData(params, serverport)
                        
                    if "checkSosData.spd" in req:
                        cmd, data = self.SOSManager.handle_checkSosData(params, serverport)
                        
                    if "outOfBlock.spd" in req:
                        cmd, data = self.SOSManager.handle_outOfBlock(params, serverport)
                        
                    if "summonOtherCharacter.spd" in req:
                        cmd, data = self.SOSManager.handle_summonOtherCharacter(params, serverport)
                        
                    if "initializeMultiPlay.spd" in req:
                        cmd, data = 0x15, "\x01"
                        
                    if data == None:
                        print repr(req)
                        print repr(cdata)
                        raise Exception("UNKNOWN CLIENT REQUEST")
                        
                    res = self.prepare_response(cmd, data)
                    # print "sending"
                    # print res
                    
                sc.sendall(res)
                sc.close()
                
            except KeyboardInterrupt:
                #sc.close()
                #gserver.close()
                raise
            except:
                #sc.close()
                traceback.print_exc()
            
            
    def handle_login(self, cdata):
        motd = "\x01\x01Welcome to ymgve's test server!\r\nMultiplayer might be working now!"
        return 0x01, motd + "\x00"
        
    def handle_charinit(self, cdata):
        params = get_params(cdata)
        charname = params["characterID"] + params["index"][0]
        
        data = charname + "\x00"
        return 0x17, data
        
    def handle_qwcdata(self, cdata):
        data = ""
        #testparams = (0x5e, 0x81, 0x70, 0x7e, 0x7a, 0x7b, 0x00)
        testparams = (0xff, -0xff, -0xffff, -0xffffff, -0x7fffffff, 0, 0)
        
        for i in xrange(7):
            data += struct.pack("<ii", testparams[i], 0)
            
        return 0x0e, data
        
    def handle_getReplayList(self, cdata):
        params = get_params(cdata)
        blockID = make_signed(int(params["blockID"]))
        replayNum = int(params["replayNum"])
        print blockID, replayNum
        
        data = struct.pack("<I", replayNum)
        for i in xrange(replayNum):
            header = random.choice(self.replayheaders[blockID])
            data += header.to_bin()
            
        return 0x1f, data
        
    def handle_getReplayData(self, cdata):
        params = get_params(cdata)
        ghostID = int(params["ghostID"])
        print ghostID
        
        ghostdata = self.replaydata[ghostID]
        data = struct.pack("<II", ghostID, len(ghostdata)) + ghostdata
            
        return 0x1e, data
        
# 'POST /cgi-bin/summonOtherCharacter.spd HTTP/1.1'
# 'ghostID=1234564&NPRoomID=/////05YUlYFFQyAAAABAQAAAAAEgAAAAgEAAAAAAIAAAAYBAAAAAAAAAAAAAQAAACcVAAAAAQEAAABOJQAAAAIBAAAAdTUAAAADAQAAAJxFAAAABAEAAADDVQAAAAUBAAAA6m
# UAAAAGAQAAARF1AAAABwEAAAE4hQAAAAgEAAB5AG0AZwB2AGUAAAB5AG0AZwB2AGUAAAAQAAAAAAAAAAAAAQACAAB8/Q===??&ver=100&\x00'

    def prepare_response(self, cmd, data):
        # The official servers were REALLY inconsistent with the data length field
        # I just set it to what seems to be the correct value and hope for the best,
        # has been working so far
        data = chr(cmd) + struct.pack("<I", len(data) + 5) + data
        
        # The newline at the end here is important for some reason
        # - standard responses won't work without it
        # - bootstrap response won't work WITH it
        return self.add_headers(base64.b64encode(data) + "\n")

    def prepare_response_bootstrap(self, data):
        return self.add_headers(base64.b64encode(data))
        
    def add_headers(self, data):
        res  = "HTTP/1.1 200 OK\r\n"
        res += "Date: " + strftime("%a, %d %b %Y %H:%M:%S GMT", gmtime()) + "\r\n"
        res += "Server: Apache\r\n"
        res += "Content-Length: %d\r\n" % len(data)
        res += "Connection: close\r\n"
        res += "Content-Type: text/html; charset=UTF-8\r\n"
        res += "\r\n"
        res += data
        return res
        
server = Server()
server.run()