"""Demo: 3 ATMs all try to use the shared account at once.

The actual verification lives in test_mutex.py.
"""
import time
from node import Node, SharedAccount

account = SharedAccount()
names = ["ATM 1", "ATM 2", "ATM 3"]

# Create the 3 ATMs
nodes = []
for i in range(3):
    nodes.append(Node(i, names[i], account))

# Tell each node who its peers are (everyone except itself)
for node in nodes:
    for other in nodes:
        if other is not node:
            node.peers.append(other)

# Everyone wants to edit, then start the threads
for node in nodes:
    node.wants_edit = True
for node in nodes:
    node.start()

# Wait until all three have edited
while not all(node.done for node in nodes):
    time.sleep(0.05)

for node in nodes:
    node.stop()
for node in nodes:
    node.join()

print("\nEdit order:", account.edit_order)
