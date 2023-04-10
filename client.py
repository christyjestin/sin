import os
import socket
import threading
import sys
import types
import selectors
from common import *

is_client = True


class Client:
    def __init__(self, p_0=CLIENT_FACING_PORT_0, p_1=CLIENT_FACING_PORT_1, p_2=CLIENT_FACING_PORT_2,
                 server_addr_0=SERVER_ADDR_0, server_addr_1=SERVER_ADDR_1, server_addr_2=SERVER_ADDR_2):
        self.username = ''
        # server that starts off as leader, 0 by default
        self.leader = 0
        self.server_addresses = [server_addr_0, server_addr_1, server_addr_2]
        self.ports = [p_0, p_1, p_2]

        self.sockets = [socket.socket(
            socket.AF_INET, socket.SOCK_STREAM) for _ in range(3)]
        for i in range(3):
            # connect and initiate stream
            try:
                self.sockets[i].connect((self.server_addresses[i], self.ports[i]))
                print(f"Connected to server {i} at {self.server_addresses[i], self.ports[i]}")
            except ConnectionRefusedError:
                print(f"Connection refused by server {i}")

        self.stop_listening = False  # boolean to tell listener threads when user logs out
        self.all_dead = False # boolean indicating whether all servers have gone down
        self.has_heartbeat = [True, True, True] # array of booleans indicating whether each server has a heartbeat
        h = threading.Thread(target=self.HeartBeat)
        h.daemon = True
        h.start()

    # this encodes a method call, sends it to the server, and finally decodes and returns
    # the server's response. Takes in a method name and the args to be passed to the method
    def run_service(self, method, args):
        assert method in SERVER_METHODS
        # SERVER_METHODS is a list of services/methods exposed by the server
        # grabbing the index of a method from this list gives a unique integer code
        # for the method in question
        method_code = SERVER_METHODS.index(method)
        transmission = str((is_client, method_code, args)).encode("utf-8")
        data = None
        while data is None:
            if self.all_dead:
                raise Exception('All Servers are Dead')
            # try or retry transmission with new leader
            self.sockets[self.leader].sendall(transmission)
            data = self.sockets[self.leader].recv(1024)
        return eval(data.decode("utf-8"))

    # Create an account with the given username.
    def CreateAccount(self, usr=''):
        return self.run_service("CreateAccount", (usr,))

    # Delete the account with the client username.
    def DeleteAccount(self):
        success = self.run_service("DeleteAccount", (self.username,))
        if success:
            self.username = ''
        return success

    # List accounts on the server that match the wildcard
    def ListAccounts(self, wildcard='.*'):
        return self.run_service("ListAccounts", (wildcard,))

    # Login to the server with the given username.
    def Login(self, usr):
        success = self.run_service("Login", (usr,))
        if success:
            self.username = usr
        return success

    # Logout of the server.
    def Logout(self):
        success = self.run_service("Logout", (self.username,))
        if success:
            self.username = ''
        return success

    # Send a message to the given recipient.
    def SendMessage(self, recipient, message):
        return self.run_service("SendMessage", (self.username, recipient, message))

    # Start a new chat connection along the given socket with the given server
    def InitiateChatConnection(self, sock, server_addr):
        sel = selectors.DefaultSelector()
        # STREAM_CODE is a code for the ChatStream method call on the server
        transmission = str((is_client, STREAM_CODE, (self.username,))).encode("utf-8")
        sock.sendall(transmission)
        # setup selector to listen for read events
        data = types.SimpleNamespace(addr=server_addr, inb=b"", outb=b"")
        events = selectors.EVENT_READ
        sel.register(sock, events, data=data)
        return sel

    # Listen for messages from the server.
    def ListenForMessages(self):
        # try to connect with all servers
        stream_sockets = [socket.socket(socket.AF_INET, socket.SOCK_STREAM) for _ in range(3)]
        for i in range(3):
            try:
                stream_sockets[i].connect((self.server_addresses[i], self.ports[i]))
            except ConnectionRefusedError:
                pass
        leader = self.leader
        sel = self.InitiateChatConnection(stream_sockets[leader], self.server_addresses[leader])
        # keep listening until either you're told to stop listening because client is logging out or all servers are down
        while not (self.stop_listening or self.all_dead):
            # when heartbeat thread changes the leader, initiate a new chat connection
            if leader != self.leader:
                leader = self.leader
                sel = self.InitiateChatConnection(stream_sockets[leader], self.server_addresses[leader])
            events = sel.select(timeout=None)
            for key, mask in events:
                # data is none when the event is a new connection
                if key.data is None:
                    raise Exception("Shouldn't be accepting connections to socket reserved for listening to messages")
                data = stream_sockets[self.leader].recv(1024)
                if not data: break
                msg = eval(data.decode("utf-8"))
                assert isinstance(msg, SingleMessage)
                print("\n[" + msg.sender + "]: " + msg.message)

    # run the heart beat thread
    def HeartBeat(self):
        # connect to all servers
        sockets = [socket.socket(socket.AF_INET, socket.SOCK_STREAM)for _ in range(3)]
        transmission = str((is_client, HEARTBEAT_CODE, tuple())).encode("utf-8")
        for i in range(3):
            try:
                sockets[i].connect((self.server_addresses[i], self.ports[i]))
            except ConnectionRefusedError:
                sockets[i] = None
                self.has_heartbeat[i] = False
        while not self.all_dead:
            # check for heartbeat from all 3 servers if they haven't already gone down
            # this is indicated by the index in the socket list being set to None
            for i in range(3):
                if sockets[i]:
                    sockets[i].sendall(transmission)
                    try:
                        data = sockets[i].recv(1)
                    except ConnectionResetError:
                        data = None
                    if not data:
                        print(f"Server {i} has died")
                        self.has_heartbeat[i] = False
                        sockets[i] = None
            # if the leader has gone down, select a new leader via carousel i.e. keep checking the next
            # server in line (with wrap around) for a heartbeat until there's a new leader
            if not self.has_heartbeat[self.leader]:
                if any(self.has_heartbeat):
                    i = (self.leader + 1) % 3
                    j = (self.leader + 2) % 3
                    self.leader = i if self.has_heartbeat[i] else j
                else:
                    self.all_dead = True

    # Print the menu for the client.
    def printMenu(self):
        print('1. Create Account')
        print('2. List All Accounts')
        print('3. List Account by Wildcard')
        print('4. Delete Account')
        print('5. Login')
        print('6. Send Message')
        print('7. Exit / Logout')

# Run the client.


def run():
    client = Client()
    client.printMenu()
    user_input = input("Enter option: ")
    if user_input in ['1', '2', '3', '4', '5', '6', '7']:
        rpc_call = int(user_input)
    else:
        rpc_call = 0

    while rpc_call != 7:
        # create account
        if rpc_call == 1:
            name = input("Enter username: ")
            if client.CreateAccount(name):
                print("Account created successfully")
            else:
                print("Account creation failed")

        # list accounts
        elif rpc_call == 2:
            for account in client.ListAccounts():
                print(account)

        # list accounts by wildcard
        elif rpc_call == 3:
            wildcard = input("Enter wildcard: ")
            for account in client.ListAccounts(wildcard):
                print(account)

        # delete account
        elif rpc_call == 4:
            if client.username == '':
                print("You must be logged in to delete your account")
            else:
                if client.DeleteAccount():
                    print("Account deleted successfully")
                else:
                    print("Account deletion failed")

        # login
        elif rpc_call == 5:
            usr = input("Enter username: ")
            if client.Login(usr):
                print("Login successful")
                # start a thread to listen for messages
                t = threading.Thread(target=client.ListenForMessages)
                t.daemon = True
                t.start()
            else:
                print("Login failed. Username might not exist.")

        # send message
        elif rpc_call == 6:
            if client.username == '':
                print("You must be logged in to send messages")
            else:
                recipient = input("Enter recipient: ")
                message = input("Enter message: ")
                if client.SendMessage(recipient, message):
                    print("Message sent successfully")
                else:
                    print("Message failed to send")

        client.printMenu()
        user_input = input("Enter option: ")
        if user_input in ['1', '2', '3', '4', '5', '6', '7']:
            rpc_call = int(user_input)
        else:
            rpc_call = 0

    # Logout if the user is logged in
    if client.username != '':
        print(client.Logout())
    # stop listening for messages
    client.stop_listening = True
    print('Exiting...')
    sys.exit(0)

# run the client
if __name__ == '__main__':
    if len(sys.argv) == 1:
        run()
    else:
        print("This program does not take command line arguments")
