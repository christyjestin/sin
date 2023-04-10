import socket
import selectors
import sys
import types
import re
from threading import Lock, Thread
from collections import defaultdict
from common import *
import os
import time


class Server():
    # initialize the server with empty users, chats, and online lists
    def __init__(self, id, server_addr_0=SERVER_ADDR_0, server_addr_1=SERVER_ADDR_1, server_addr_2=SERVER_ADDR_2,
                 cfp_0=CLIENT_FACING_PORT_0, cfp_1=CLIENT_FACING_PORT_1, cfp_2=CLIENT_FACING_PORT_2,
                 sfp_0=SERVER_FACING_PORT_0, sfp_1=SERVER_FACING_PORT_1, sfp_2=SERVER_FACING_PORT_2):
        self.id = id
        self.addresses = [server_addr_0, server_addr_1, server_addr_2]

        self.client_facing_ports = [cfp_0, cfp_1, cfp_2]
        self.server_facing_ports = [sfp_0, sfp_1, sfp_2]
        self.sel = selectors.DefaultSelector()
        self.server_facing_sockets = [socket.socket(
            socket.AF_INET, socket.SOCK_STREAM) for _ in range(2)]
        self.client_facing_socket = socket.socket(
            socket.AF_INET, socket.SOCK_STREAM)

        # listen and connect to server facing ports while listening only on client facing ports
        if self.id == 0:
            self.listen_wrapper([*self.server_facing_sockets, self.client_facing_socket],
                                [*self.server_facing_ports[:2], self.client_facing_ports[self.id]])
        elif self.id == 1:
            self.listen_wrapper([self.server_facing_sockets[0], self.client_facing_socket],
                                [self.server_facing_ports[2], self.client_facing_ports[self.id]])
            self.connect_wrapper(
                self.server_facing_sockets[1:2], self.addresses[0:1], self.server_facing_ports[0:1])
        elif self.id == 2:
            self.listen_wrapper([self.client_facing_socket], [
                                self.client_facing_ports[self.id]])
            self.connect_wrapper(self.server_facing_sockets,
                                 self.addresses[:2], self.server_facing_ports[1:])
        else:
            raise ValueError(f"Invalid Id: {self.id}")

        self.users_lock = Lock()  # lock for both self.users and self.online
        self.users = set()
        self.online = set()
        self.chat_locks = defaultdict(Lock) # locks for each k, v pair in self.chats
        self.chats = defaultdict(list)

        self.log_dir = "Server_" + str(self.id) + "_Logs"
        self.users_log = self.log_dir + "/users.txt"
        self.unsent_messages_log_dir = self.log_dir + "/unsent_messages"


        # check for existing log files
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
            os.makedirs(self.unsent_messages_log_dir)
        else:
            # check for existing users and load them
            if os.path.exists(self.users_log):
                # first get all the users
                with open(self.users_log, "r") as file:
                    self.users = set(line.rstrip("\n") for line in file)

    # a wrapper function for connecting sockets w/ selector
    def connect_wrapper(self, sockets, addrs, ports):
        for socket, addr, port in zip(sockets, addrs, ports):
            try:
                socket.connect((addr, port))
                data = types.SimpleNamespace(addr=(addr, port), inb=b"", outb=b"")
                events = selectors.EVENT_READ | selectors.EVENT_WRITE
                self.sel.register(socket, events, data=data)
            except ConnectionRefusedError:
                print(f"Connection refused on address {addr} and port {port}")

    # a wrapper function for binding and listening to sockets w/ selector
    def listen_wrapper(self, sockets, ports):
        for sock, port in zip(sockets, ports):
            sock.bind((self.addresses[self.id], port))
            sock.listen()
            print(f"Listening on {(self.addresses[self.id], port)}")
            sock.setblocking(False)
            self.sel.register(sock, selectors.EVENT_READ, data=None)

    # a wrapper function for accepting sockets w/ selector
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
            # retry on initial error since connection may be finnicky
            try:
                recv_data = sock.recv(1024)
            except ConnectionResetError:
                recv_data = sock.recv(1024)
            if recv_data:
                is_client, method_code, args = eval(recv_data.decode("utf-8"))
                # if we're receiving a method call from the client, we need to respond
                # otherwise we mirror the method call but don't respond
                if is_client:
                    if method_code == STREAM_CODE:
                        # start up the thread and pass the data object, so the thread can write to it
                        t = Thread(target=self.ChatStream, args=(*args, data))
                        t.daemon = True
                        t.start()
                    elif method_code == HEARTBEAT_CODE:
                        data.outb += b'1'
                    else:
                        output = self.run_server_method(method_code, args)
                        data.outb += str(output).encode("utf-8")
                        # forward method calls to other servers since you're the leader
                        # if you're getting calls from the client
                        invalid = []
                        for server_sock in self.server_facing_sockets:
                            try:
                                server_sock.sendall(
                                    str((False, method_code, args)).encode("utf-8"))
                            except OSError:
                                invalid.append(server_sock)
                        # remove invalid sockets for other servers that have crashed
                        for server_sock in invalid:
                            self.server_facing_sockets.remove(server_sock)
                # process a forwarded method call without responding
                else:
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
        return getattr(self, SERVER_METHODS[method_code])(*args)

    # report failure if account already exists and add user otherwise
    def CreateAccount(self, user):
        with self.users_lock:
            success = user not in self.users
            if success:
                print("adding user: " + user)
                self.users.add(user)
                # add user to log file
                with open(self.users_log, mode = "a") as file:
                    print(user, file=file)
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
                        # delete undelivered chats if you are deleting the account
                        del self.chats[user]
                del self.chat_locks[user]
                # update user log to exclude the deleted account
                with open(self.users_log, "w") as file:
                    for el in list(self.users):
                        print(el, file=file)
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
        if success:
            # try loading in unsent message log
            filepath = self.unsent_messages_log_dir + '/' + user + '.txt'
            if os.path.exists(filepath):
                with open(filepath, "r") as f:
                    with self.chat_locks[user]:
                        self.chats[user] = [eval(line.rstrip("\n")) for line in f]
                os.remove(filepath)
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
            with self.users_lock:
                # if the user is offline, then write the message to the log for persistence
                if recipient not in self.online:
                    with open(self.unsent_messages_log_dir + "/" + recipient + ".txt", mode="a") as f:
                        f.write(str(message) + '\n')
            return True

    # report failure if account doesn't exist and start chat stream otherwise
    def ChatStream(self, user, data_stream):
        # always make sure to release this; note that this needs to intermittently release
        self.users_lock.acquire(blocking=True)
        while user in self.online:
            assert user in self.users, "user does not exist or no longer exists"
            # release so that the streams aren't constantly holding onto the lock
            self.users_lock.release()
            with self.chat_locks[user]:
                if self.chats[user]:
                    msg = self.chats[user].pop(0)
                    data_stream.outb += str(msg).encode("utf-8")
            # wait slightly to avoid sending two messages in same outbound message
            time.sleep(0.01)
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
