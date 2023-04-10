# Strength in Numbers
A client/server application for a replicated chat service. The third design project for CS 262 @ Harvard

``python3 server.py [0, 1, or 2]" for servers (boot up in order of 0, then 1, then 2
``python3 client.py" for clients

## How to Use

### Preparation + Launching Server / Client
The user first clones this repository, then installs the required dependencies using `pip install -r requirements.txt`. Then run the server either in the background (`python server.py`) or in another terminal. Next run your client in another terminal using (`python client.py [server_ip]`). Note that after launching, the server will display the ip it is running on, which must be used as the argument for the script launching the client. 

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
