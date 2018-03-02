import socket, traceback, struct, base64, random, cStringIO, zlib, select, time, logging
from time import gmtime, strftime

from emu.Util import *

from emu.GhostManager import *
from emu.MessageManager import *
from emu.PlayerManager import *
from emu.SOSManager import *

logging.basicConfig(level=logging.DEBUG,
                    format="[%(asctime)s][%(levelname)s] %(message)s",
                    filename="emulator.log")

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)

logging.getLogger("").addHandler(stream_handler)

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
        self.logpacket("sent data", data)
        self.sc.sendall(data)
        
    def recv_line(self):
        line = ""
        while True:
            c = self.recv(1)
            if len(c) == 0:
                logging.warning("DISCONNECT at line %r" % line)
                raise Exception("DISCONNECT")
            line += c
            if line.endswith("\r\n"):
                line = line[:-2]
                self.logpacket("recv line", line)
                return line
            
    def recv_all(self, size):
        res = ""
        while len(res) < size:
            data = self.recv(size - len(res))
            if len(data) == 0:
                logging.warning("DISCONNECT %r" % res)
                raise Exception("DISCONNECT")
            res += data
            
        self.logpacket("recv data", res)
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
    
    def logpacket(self, msg, data):
        open("packetlog.log", "a").write("[%s][c %r][s %r] %s %r\n" % (time.asctime(time.gmtime()), self.sc.getpeername(), self.sc.getsockname(), msg, data))

class Server(object):
    def __init__(self):
        self.GhostManager = GhostManager()
        self.MessageManager = MessageManager()
        self.SOSManager = SOSManager()
        self.PlayerManager = PlayerManager()
        self.replayheaders = {}
        self.replaydata = {}
        self.players = {}
        
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
                
    def run(self):
        servers = []
        for port in (SERVER_PORT_BOOTSTRAP, SERVER_PORT_US, SERVER_PORT_EU, SERVER_PORT_JP):
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(('', port))
            server.listen(5)
            servers.append(server)
        
        logging.info("Server listening")

        while True:
            try:
                readable, _, _ = select.select(servers, [], [])
                ready_server = readable[0]
                serverport = ready_server.getsockname()[1]
                
                client_sock, client_addr = ready_server.accept()
                client_ip = client_addr[0]
                
                sc = ImpSock(client_sock, "client")
                
                req = sc.recv_line()
                logging.debug("got connect from %r to %r request %r" % (client_addr, serverport, req))
                
                clientheaders = sc.recv_headers()
                        
                cdata = sc.recv_all(int(clientheaders["Content-Length"]))
                cdata = decrypt(cdata)
                sc.logpacket("decr data", cdata)
                
                
                if serverport == SERVER_PORT_BOOTSTRAP:
                    data = open("info.ss", "rb").read()
                    res = self.prepare_response_bootstrap(data)
                else:
                    params = get_params(cdata)
                    clientcmd = req.split()[1].split("/")[-1]
                    
                    if "characterID" in params:
                        self.players[client_ip] = params["characterID"]
                        
                    if client_ip not in self.players:
                        self.players[client_ip] = "[%s]" % client_ip
                        
                    characterID = self.players[client_ip]
                    
                    if clientcmd == "login.spd":
                        cmd, data = self.handle_login(params)
                    elif clientcmd == "initializeCharacter.spd":
                        cmd, data, characterID = self.PlayerManager.handle_initializeCharacter(params)
                        self.players[client_ip] = characterID
                    elif clientcmd == "getQWCData.spd":
                        cmd, data = self.PlayerManager.handle_getQWCData(params, characterID)
                    elif clientcmd == "addQWCData.spd":
                        cmd, data = 0x09, "\x01"
                    elif clientcmd == "getMultiPlayGrade.spd":
                        cmd, data = self.PlayerManager.handle_getMultiPlayGrade(params)
                    elif clientcmd == "getBloodMessageGrade.spd":
                        cmd, data = self.PlayerManager.handle_getBloodMessageGrade(params)
                    elif clientcmd == "getTimeMessage.spd":
                        cmd, data = self.handle_getTimeMessage(params)
                    elif clientcmd == "getAgreement.spd": # not observed in the wild, mostly guessing
                        cmd, data = 0x01, "\x01\x01Hello!!\r\n\x00"
                    elif clientcmd == "addNewAccount.spd": # not observed in the wild, doesn't really work
                        cmd, data = 0x01, "\x01\x01Hello!!\r\n\x00"
                        
                    elif clientcmd == "getBloodMessage.spd":
                        cmd, data = self.MessageManager.handle_getBloodMessage(params)
                    elif clientcmd == "addBloodMessage.spd":
                        cmd, data, custom_command = self.MessageManager.handle_addBloodMessage(params)
                        
                    elif clientcmd == "updateBloodMessageGrade.spd":
                        cmd, data = self.MessageManager.handle_updateBloodMessageGrade(params, self)
                    elif clientcmd == "deleteBloodMessage.spd":
                        cmd, data = self.MessageManager.handle_deleteBloodMessage(params)
                        
                    elif clientcmd == "getReplayList.spd":
                        cmd, data = self.handle_getReplayList(cdata)
                    elif clientcmd == "getReplayData.spd":
                        cmd, data = self.handle_getReplayData(cdata)
                    elif clientcmd == "addReplayData.spd":
                        cmd, data = 0x1d, "01000000".decode("hex")
                        
                    elif clientcmd == "getWanderingGhost.spd":
                        cmd, data = self.GhostManager.handle_getWanderingGhost(params)
                    elif clientcmd == "setWanderingGhost.spd":
                        cmd, data = self.GhostManager.handle_setWanderingGhost(params)
                        
                    elif clientcmd == "getSosData.spd":
                        cmd, data = self.SOSManager.handle_getSosData(params, serverport)
                    elif clientcmd == "addSosData.spd":
                        cmd, data = self.SOSManager.handle_addSosData(params, serverport, self)
                    elif clientcmd == "checkSosData.spd":
                        cmd, data = self.SOSManager.handle_checkSosData(params, serverport)
                    elif clientcmd == "outOfBlock.spd":
                        cmd, data = self.SOSManager.handle_outOfBlock(params, serverport)
                    elif clientcmd == "summonOtherCharacter.spd":
                        cmd, data = self.SOSManager.handle_summonOtherCharacter(params, serverport, characterID)
                    elif clientcmd == "summonBlackGhost.spd":
                        cmd, data = self.SOSManager.handle_summonBlackGhost(params, serverport, characterID)
                    elif clientcmd == "initializeMultiPlay.spd":
                        logging.info("Player %r started a multiplayer session successfully" % characterID)
                        cmd, data = 0x15, "\x01"
                    elif clientcmd == "finalizeMultiPlay.spd":
                        cmd, data = self.PlayerManager.handle_finalizeMultiPlay(params)
                    elif clientcmd == "updateOtherPlayerGrade.spd":
                        cmd, data = self.PlayerManager.handle_updateOtherPlayerGrade(params, characterID)
                    else:
                        logging.error("UNKNOWN CLIENT REQUEST")
                        logging.error("req %r" % req)
                        logging.error("cdata %r" % cdata)
                        raise Exception("UNKNOWN CLIENT REQUEST")
                        
                    res = self.prepare_response(cmd, data)
                    
                sc.sendall(res)
                sc.close()
                
            except KeyboardInterrupt:
                sc.close()
                raise
            except:
                sc.close()
                tb = traceback.format_exc()
                logging.error("Exception! Traceback:\n%s" % tb)
            
    def handle_login(self, params):
        motd  = "Welcome to ymgve's test server!\r\n"
        motd += "This is a temporary server, it will eventually be shut\r\n"
        motd += "down and its source code published.\r\n"

        total, blockslist = self.GhostManager.get_current_players()
        motd2  = "Current players online: %d\r\n" % total
        motd2 += "Popular areas:\r\n"
        for count, blockID in blockslist[::-1][0:5]:
             motd2 += "%4d %s\r\n" % (count, blocknames[blockID])
             
        # first byte
        # 0x00 - present EULA, create account (not working)
        # 0x01 - present MOTD, can be multiple
        # 0x02 - "Your account is currently suspended."
        # 0x03 - "Your account has been banned."
        # 0x05 - undergoing maintenance
        # 0x06 - online service has been terminated
        # 0x07 - network play cannot be used with this version
        
        return 0x02, "\x01" + "\x02" + motd + "\x00" + motd2 + "\x00"
        
    def handle_getTimeMessage(self, params):
        # first byte
        # 0x00 - nothing
        # 0x01 - undergoing maintenance
        # 0x02 - online service has been terminated

        return 0x22, "\x00\x00\x00"
        
    def handle_getReplayList(self, cdata):
        params = get_params(cdata)
        blockID = make_signed(int(params["blockID"]))
        replayNum = int(params["replayNum"])
        
        data = struct.pack("<I", replayNum)
        for i in xrange(replayNum):
            header = random.choice(self.replayheaders[blockID])
            data += header.to_bin()
            
        return 0x1f, data
        
    def handle_getReplayData(self, cdata):
        params = get_params(cdata)
        ghostID = int(params["ghostID"])
        
        ghostdata = self.replaydata[ghostID]
        data = struct.pack("<II", ghostID, len(ghostdata)) + ghostdata
            
        return 0x1e, data
        
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