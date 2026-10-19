"""The shared resource: one bank account that 3 ATMs withdraw from.

BankAccount extends SharedAccount (from node.py), which the algorithms
already use. The nodes already call start_edit() when they enter the
critical section and end_edit() when they leave, with a short wait in
between, so a withdrawal maps onto that like this:

    start_edit()        -> READ the balance
    (node waits 0.3s)   -> "wait briefly" (the ATM counts the cash)
    end_edit()          -> WRITE the new balance
"""
from node import SharedAccount

START_BALANCE = 1000
WITHDRAW_AMOUNT = 100


class BankAccount(SharedAccount):
    def __init__(self, balance=START_BALANCE, amount=WITHDRAW_AMOUNT):
        super().__init__()              # keeps the overlap check + edit order
        self.balance = balance
        self.amount = amount
        self.read_value = None          # balance the current ATM read
        self.current_atm = None         # which ATM is in the critical section
        self.history = []               # (atm, balance read, balance written)

    def start_edit(self, name):
        super().start_edit(name)
        self.current_atm = name
        self.read_value = self.balance          # step 1: read

    def end_edit(self):
        # step 3: write. Decline if there isn't enough money.
        new_balance = self.read_value
        if self.read_value >= self.amount:
            new_balance = self.read_value - self.amount
        self.balance = new_balance
        self.history.append((self.current_atm, self.read_value, new_balance))
        self.current_atm = None
        super().end_edit()
