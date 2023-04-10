import socket
import selectors
import sys
import types
import re
from threading import Lock, Thread
from collections import defaultdict
from common import *


# Non GRPC implementation
class Server():

    # initialize the server with empty users, chats, and online lists
    def __init__(self, id, server_addr_0=SERVER_ADDR_0, server_addr_1=SERVER_ADDR_1,
                 server_addr_2=SERVER_ADDR_2, p_0=PORT_0, p_1=PORT_1, p_2=PORT_2):
        self.id = id
        self.addresses = [server_addr_0, server_addr_1, server_addr_2]
        self.ports = [p_0, p_1, p_2]
        self.server_sockets = []
        # connect to lower ranked servers only
        for i in range(self.id):
            self.server_sockets.append(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
            self.server_sockets[i].connect((self.addresses[i], self.ports[i]))

        # create socket for itself
        lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lsock.bind((self.addresses[self.id], self.ports[self.id]))
        lsock.listen()
        print(
            f"Listening on {(self.addresses[self.id], self.ports[self.id])}")
        lsock.setblocking(False)
        self.sel = selectors.DefaultSelector()
        self.sel.register(lsock, selectors.EVENT_READ, data=None)

        # only remember the addresses and ports of other servers
        self.addresses.pop(self.id)
        self.ports.pop(self.id)

        self.server_keys = []
        self.users_lock = Lock() # lock for both self.users and self.online
        self.users = set()
        self.chat_locks = defaultdict(Lock) # locks for each k, v pair in self.chats
        self.chats = defaultdict(list)
        self.online = set()

    # a wrapper function for accepting sockets with some additional configuration
    def accept_wrapper(self, sock):
        conn, addr = sock.accept()
        print(f"Accepted connection from {addr}")
        conn.setblocking(False)
        data = types.SimpleNamespace(addr=addr, inb=b"", outb=b"")
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        key = self.sel.register(conn, events, data=data)
        if addr in self.addresses:
            self.server_keys.append(key)

    # service a socket that is connected: handle inbound and outbound data
    # while running any necessary chat server methods
    def service_connection(self, key, mask):
        sock = key.fileobj
        data = key.data
        if mask & selectors.EVENT_READ:
            recv_data = sock.recv(1024)  # Should be ready to read
            if recv_data:
                is_client, method_code, args = eval(recv_data.decode("utf-8"))
                if is_client:
                    if method_code != STREAM_CODE:
                        output = self.run_server_method(method_code, args)
                        data.outb += str(output).encode("utf-8")
                        # send output to other servers
                        for server_key in self.server_keys:
                            server_key.data.outb += recv_data
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
            print(self.users)
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
    serve(sys.argv[1])
