from collections import namedtuple

SERVER_ADDR_0 = "192.168.1.17"
SERVER_ADDR_1 = "192.168.1.17"
SERVER_ADDR_2 = "192.168.1.17"


CLIENT_FACING_PORT_0 = 50051
CLIENT_FACING_PORT_1 = 50052
CLIENT_FACING_PORT_2 = 50053

SERVER_FACING_PORT_0 = 50054
SERVER_FACING_PORT_1 = 50055
SERVER_FACING_PORT_2 = 50056

# type for messages
SingleMessage = namedtuple("SingleMessage", ["sender", "message"])

# methods that will be exposed to the client; our analog to services
SERVER_METHODS = ['CreateAccount', 'ListAccounts', 'DeleteAccount', 'Login', 'Logout', 'SendMessage', 'ChatStream']
STREAM_CODE = SERVER_METHODS.index('ChatStream')

HEARTBEAT_CODE = 77