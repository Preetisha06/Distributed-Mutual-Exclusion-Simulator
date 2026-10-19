"""Local OS version: 3 ATMs as 3 threads on ONE machine.

All threads share memory (the account balance), so the problem and its
fix are easy to see:
  - with NO lock, two threads can read the same balance and overwrite
    each other's withdrawal (a race condition);
  - with a semaphore, only one thread is in the critical section at a time.

Run a demo with:  python local_os.py
"""
import threading
import time

START_BALANCE = 1000
WITHDRAW_AMOUNT = 100
ROUNDS = 2                  # withdrawals per ATM
NAMES = ["ATM 1", "ATM 2", "ATM 3"]


class LocalAccount:
    def __init__(self):
        self.balance = START_BALANCE


def atm(account, name, semaphore, history):
    for _ in range(ROUNDS):
        if semaphore:
            semaphore.acquire()                 # enter critical section (wait if taken)

        balance_read = account.balance          # 1. read
        time.sleep(0.05)                        # 2. wait briefly (other threads run now!)
        account.balance = balance_read - WITHDRAW_AMOUNT   # 3. write
        history.append((name, balance_read, account.balance))

        if semaphore:
            semaphore.release()                 # leave critical section


def run_local(use_lock):
    """Run 3 ATM threads. Returns the final balance, expected balance and history."""
    account = LocalAccount()
    history = []
    # A semaphore starting at 1 only lets one thread in at a time (a mutex)
    semaphore = threading.Semaphore(1) if use_lock else None

    threads = []
    for name in NAMES:
        threads.append(threading.Thread(target=atm,
                                        args=(account, name, semaphore, history)))
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    expected = START_BALANCE - len(NAMES) * ROUNDS * WITHDRAW_AMOUNT
    return {"final": account.balance, "expected": expected, "history": history}


if __name__ == "__main__":
    for use_lock in (False, True):
        result = run_local(use_lock)
        print("WITH semaphore" if use_lock else "NO lock")
        for name, read, wrote in result["history"]:
            print(f"  {name}: read {read}, wrote {wrote}")
        print(f"  final = {result['final']}, expected = {result['expected']}")
