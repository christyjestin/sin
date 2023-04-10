# Strength in Numbers

## A client/server application for a replicated chat service (3rd design project for CS 262 @ Harvard)

Please run:

-   `python3 server.py [0, 1, or 2]` for servers (boot up in order of 0, then 1, then 2)
-   `python3 client.py` for clients

### How to Use

Simply launch the three servers and any number of clients in separate terminals or machines.

### UI:

After you launch the client, you will be shown a menu with seven options:

1. Create Account
2. List all Accounts
3. List Account by Wildcard
4. Delete Account
5. Login
6. Send Message
7. Logout + Exit

The user then types a number specifying the option they want. After that, they specify the arguments. The client sends a message to the server, the server performs the requested action, and reports back the status of the request back to the client. The user can keep on specifying options as they please. Once the user is done, they can exit by typing 7.

### Replication

All active servers are updated with events (e.g. account creation), and backup servers will take over when the leader goes down. The leader is responsible for both coordinating updates and responding to the client. The leader is chosen by the clients rather than the servers. This selection is done separately by each client, but they use the same algorithm and are constantly listening to the servers' heartbeats to determine which servers are up.

### Persistence

All active servers will log messages intended for offline users such that if the server goes down and gets revived, it will be able to use the logs to restore these unsent messages and ultimately deliver them when the user is back online. All servers also maintain a log of current users, and they use this log on reboot to instantiate the set of all users. There is no logic to resolve log discrepancies between servers or to catch a server back up to the leader if the server missed events while it was down.
