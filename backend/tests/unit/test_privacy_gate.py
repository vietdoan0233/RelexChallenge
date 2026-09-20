import threading

from app.privacy.gate import ReadWriteGate


def test_write_leases_are_serialized():
    gate = ReadWriteGate()
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()

    def first_writer():
        with gate.write_lease():
            first_entered.set()
            release_first.wait(timeout=2)

    def second_writer():
        with gate.write_lease():
            second_entered.set()

    first = threading.Thread(target=first_writer)
    second = threading.Thread(target=second_writer)
    first.start()
    assert first_entered.wait(timeout=1)
    second.start()
    assert not second_entered.wait(timeout=0.05)

    release_first.set()
    first.join(timeout=1)
    second.join(timeout=1)
    assert second_entered.is_set()
