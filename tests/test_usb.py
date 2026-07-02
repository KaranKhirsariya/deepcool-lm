class FakeWinUsbDev:
    """Mimics a pyusb device on the WinUSB backend, where kernel-driver
    queries are not implemented."""

    def __init__(self):
        self.configured = False

    def is_kernel_driver_active(self, interface):
        raise NotImplementedError

    def set_configuration(self):
        self.configured = True


def test_usb_backend_none_on_linux(dlm):
    assert dlm._usb_backend() is None


def test_usb_backend_none_when_libusb_package_missing(dlm, monkeypatch):
    # On Windows without libusb-package installed we must fall back to
    # pyusb's default discovery (None), not crash.
    monkeypatch.setattr(dlm, 'IS_WINDOWS', True)
    assert dlm._usb_backend() is None


def test_connect_survives_winusb_notimplemented(dlm, monkeypatch):
    fake = FakeWinUsbDev()
    monkeypatch.setattr(dlm.usb.core, 'find', lambda **kw: fake)
    monkeypatch.setattr(dlm.usb.util, 'claim_interface', lambda dev, i: None)
    dev = dlm.LM360()
    assert dev.connect() is True
    assert fake.configured is True
