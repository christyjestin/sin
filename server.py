import socket
import selectors
import sys
import types
import re
from threading import Lock, Thread
from collections import defaultdict
from common import *
import os


# Non GRPC implementation
class Server():

    # initialize the server with empty users, chats, and online lists
    def __init__(self, id, server_addr_0=SERVER_ADDR_0, server_addr_1=SERVER_ADDR_1,
                 server_addr_2=SERVER_ADDR_2, p_0=PORT_0, p_1=PORT_1, p_2=PORT_2,
                 c_0=CONNECT_PORT_0, c_1=CONNECT_PORT_1, c_2=CONNECT_PORT_2):
        self.id = id
        self.addresses = [server_addr_0, server_addr_1, server_addr_2]
        self.ports = [p_0, p_1, p_2]
        self.server_connection_ports = [c_0, c_1, c_2]
        self.sel = selectors.DefaultSelector()
        self.server_facing_sockets = [socket.socket(socket.AF_INET, socket.SOCK_STREAM) for _ in range(2)]
        self.client_facing_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if self.id == 0:
            self.listen_wrapper([*self.server_facing_sockets, self.client_facing_socket], 
                                [*self.server_connection_ports[:2], self.ports[self.id]])
        elif self.id == 1:
            self.listen_wrapper([self.server_facing_sockets[0], self.client_facing_socket], 
                                [self.server_connection_ports[2], self.ports[self.id]])
            self.connect_wrapper(self.server_facing_sockets[1:2], self.addresses[0:1], self.server_connection_ports[0:1])
        elif self.id == 2:
            self.listen_wrapper([self.client_facing_socket], [self.ports[self.id]])
            self.connect_wrapper(self.server_facing_sockets, self.addresses[:2], self.server_connection_ports[1:])
        else:
            raise ValueError(f"Invalid Id: {self.id}")

        self.users_lock = Lock() # lock for both self.users and self.online
        self.users = set()
        self.chat_locks = defaultdict(Lock) # locks for each k, v pair in self.chats
        self.chats = defaultdict(list)
        self.online = set()
        self.log_dir = "Server_" + str(self.id) + "_Logs"


        ### CHARLES NEW CODE ###
        # check if this is an initial bootup or reboot from server failure
        # do this by checking if folder + logs have been previously written
        if os.path.exists(self.log_dir):
            # TODO: call the function that gets server up to date using its log
            pass
        else:
            # make the directory to store the logs
            os.makedirs(self.log_dir)
        ### CHARLES NEW CODE ###

    # a wrapper function for connecting a socket
    def connect_wrapper(self, sockets, addrs, ports):
        for socket, addr, port in zip(sockets, addrs, ports):
            socket.connect((addr, port))
            data = types.SimpleNamespace(addr=(addr, port), inb=b"", outb=b"")
            events = selectors.EVENT_READ | selectors.EVENT_WRITE
            self.sel.register(socket, events, data=data)

    # a wrapper function for binding and listening to sockets
    def listen_wrapper(self, sockets, ports):
        for sock, port in zip(sockets, ports):
            sock.bind((self.addresses[self.id], port))
            sock.listen()
            print(f"Listening on {(self.addresses[self.id], port)}")
            sock.setblocking(False)
            self.sel.register(sock, selectors.EVENT_READ, data=None)

    # a wrapper function for accepting sockets with some additional configuration
    def accept_wrapper(self, sock):
        conn, (addr, port) = sock.accept()
        if sock != self.client_facing_socket:
            repl = self.server_facing_sockets.index(sock)
            self.server_facing_sockets[repl] = conn
        print(f"Accepted connection from {addr, port}")
        conn.setblocking(False)
        data = types.SimpleNamespace(addr=(addr, port), inb=b"", outb=b"")
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        self.sel.register(conn, events, data=data)

    # service a socket that is connected: handle inbound and outbound data
    # while running any necessary chat server methods
    def service_connection(self, key, mask):
        sock = key.fileobj
        data = key.data
        if mask & selectors.EVENT_READ:
            recv_data = sock.recv(1024)  # Should be ready to read
            if recv_data:
                print('server received following: ', recv_data.decode("utf-8"))
                is_client, method_code, args = eval(recv_data.decode("utf-8"))
                if is_client:
                    if method_code != STREAM_CODE:
                        output = self.run_server_method(method_code, args)
                        data.outb += str(output).encode("utf-8")
                        # send output to other servers
                        for server_sock in self.server_facing_sockets:
                            server_sock.sendall(str((False, method_code, args)).encode("utf-8"))
                    else:
                        # start up the thread and pass the data object, so the thread can write to it
                        t = Thread(target=self.ChatStream, args=(*args, data))
                        t.start()
                else:
                    # code for handling other servers sending data
                    self.run_server_method(method_code, args)
            else:
                print(f"Closing connection to {data.addr}")
                self.sel.unregister(sock)
                sock.close()
        if mask & selectors.EVENT_WRITE and data.outb:
            # handle outbound data
            sock.sendall(data.outb)
            data.outb = b''

    # run a method on the server given a code for the method and a tuple of the args to pass in
    def run_server_method(self, method_code, args):
        print(SERVER_METHODS[method_code], args)
        return getattr(self, SERVER_METHODS[method_code])(*args)

    # report failure if account already exists and add user otherwise
    def CreateAccount(self, user):
        with self.users_lock:
            success = user not in self.users
            if success:
                print("adding user: " + user)
                self.users.add(user)

                ### CHARLES NEW CODE ###

                # log to USERS that a new user has been created
                # assert os.path.exists(self.)
                ### CHARLES END NEW CODE ###
        return success

    # report failure if account doesn't exist and delete user otherwise
    def DeleteAccount(self, user):
        with self.users_lock:
            success = user in self.users
            if success:
                print("deleting user: " + user)
                self.users.discard(user)
                self.online.discard(user)
                with self.chat_locks[user]:
                    if user in self.chats:
                        del self.chats[user] # delete undelivered chats if you are deleting the account
                del self.chat_locks[user]
        return success
    
    # report failure if account doesn't exist and return list of accounts that match wildcard otherwise
    def ListAccounts(self, accountWildcard):
        # search in users for accounts that match wildcard
        pattern = re.compile(accountWildcard)
        with self.users_lock:
            accounts = list(filter(lambda user: pattern.search(user) != None, self.users))
        print("listing users: " + str(accounts))
        return accounts

    # report failure if account doesn't exist and add user to online list otherwise
    def Login(self, user):
        print("logging in user: " + user)
        with self.users_lock:
            self.online.add(user)
            success = user in self.users
        return success

    # report failure if account doesn't exist and remove user from online list otherwise
    def Logout(self, user):
        print("logging out user: " + user)
        with self.users_lock:
            success = user in self.online
            self.online.discard(user)
        return success

    # report failure if recipient doesn't exist and send message otherwise
    def SendMessage(self, sender, recipient, message):
        print(f"received message from {sender} to {recipient}: {message}")
        self.users_lock.acquire(blocking=True)
        if recipient not in self.users:
            self.users_lock.release()
            return False
        else:
            self.users_lock.release()
            message = SingleMessage(sender, message)
            with self.chat_locks[recipient]:
                self.chats[recipient].append(message)
            return True

    # report failure if account doesn't exist and start chat stream otherwise
    def ChatStream(self, user, data_stream):
        print(f"started chat stream for {user}")
        # always make sure to release this; note that this needs to intermittently release
        self.users_lock.acquire(blocking=True)
        while user in self.online:
            assert user in self.users, "user does not exist or no longer exists"
            # release so that the streams aren't constantly holding onto the lock
            self.users_lock.release()
            with self.chat_locks[user]:
                if self.chats[user]:
                    print("sending message to " + user)
                    msg = self.chats[user].pop(0)
                    data_stream.outb += str(msg).encode("utf-8")
            # reacquire lock before checking while condition
            self.users_lock.acquire(blocking=True)
        # release lock before stopping stream
        self.users_lock.release()

# start the server
def serve(id):
    server = Server(id)
    while True:
        events = server.sel.select(timeout=None)
        for key, mask in events:
            if key.data is None:
                server.accept_wrapper(key.fileobj)
            else:
                server.service_connection(key, mask)

# run the server when this script is executed
if __name__ == '__main__':
    assert len(sys.argv) == 2, "provide server id"
    serve(int(sys.argv[1]))
