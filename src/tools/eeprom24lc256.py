#!/usr/bin/env python3
"""A 24LC256 I2C EEPROM on the right joystick port, as the SaveKey wires it.

Pin 3 = SDA = SWCHA bit 2, pin 4 = SCL = SWCHA bit 3 (Stella SaveKey.cxx).
The console side is open-drain by hand: the ROM keeps the SWCHA latch bits at 0
and drives a line LOW by setting its SWACNT bit (output) or RELEASES it by
clearing the bit (input, pulled up by the key). The bus level of a line is
therefore  master_released AND slave_released.

The chip is modelled at bit level and records anything it would not accept in
`violations`: SDA changing while SCL is high other than START / STOP, a latch
bit that would drive a line high, other pins turned into outputs, and a write
burst that crosses a 64-byte page (a real chip wraps inside the page silently;
our ROM must never rely on that).

After a write's STOP the chip is busy for `WRITE_CYCLE_CYCLES` CPU cycles
(5 ms at 1.19 MHz) and NACKs its control byte meanwhile (ACK polling).
`clock` is a callable returning the CPU cycle count (mpu.processorCycles).
"""

SDA_BIT = 0x04
SCL_BIT = 0x08
WRITE_CYCLE_CYCLES = 5966
PAGE = 64


class Eeprom24LC256:
    def __init__(self, clock=lambda: 0, present=True, size=32768):
        self.mem = bytearray([0xFF]) * size
        self.size = size
        self.clock = clock
        self.present = present
        self.violations = []
        self.swacnt = 0
        self.sda_slave = 1
        self.mode = "IDLE"       # IDLE | RX | TX | WAIT_STOP
        self.purpose = None      # CTRL | ADDR_H | ADDR_L | DATA
        self.rises = 0           # SCL rising edges seen in the current byte
        self.shift = 0
        self.addr = 0
        self.rw = 0
        self.ack_out = False     # slave is driving ACK this 9th clock
        self.master_ack = 1
        self.busy_until = -1
        self.write_start = None
        self.write_len = 0
        self.writes = []         # (address, bytes) per write burst
        self.starts = self.stops = 0

    # ---- bus levels -------------------------------------------------------
    def sda(self):
        m = 0 if self.swacnt & SDA_BIT else 1
        return m & (self.sda_slave if self.present else 1)

    def scl(self):
        return 0 if self.swacnt & SCL_BIT else 1

    # ---- console register access -----------------------------------------
    def read_swcha(self):
        v = 0xF3
        if self.sda():
            v |= SDA_BIT
        if self.scl():
            v |= SCL_BIT
        return v

    def write_swcha(self, v):
        if v & (SDA_BIT | SCL_BIT):
            self.violations.append("SWCHA latch bit set for SDA/SCL (drives high)")

    def write_swacnt(self, v):
        v &= 0xFF
        if v & ~(SDA_BIT | SCL_BIT) & 0xFF:
            self.violations.append(f"SWACNT ${v:02X} makes other pins outputs")
        sda0, scl0 = self.sda(), self.scl()
        self.swacnt = v
        sda1, scl1 = self.sda(), self.scl()
        if not self.present:
            return
        if scl0 and scl1 and sda0 != sda1:          # START / STOP
            self._start() if sda0 and not sda1 else self._stop()
        elif sda0 != sda1 and scl1:                  # data edge, SCL high
            self.violations.append("SDA changed while SCL high")
        if scl0 == 0 and scl1 == 1:
            self._rise(sda1)
        elif scl0 == 1 and scl1 == 0:
            self._fall()

    # ---- protocol engine --------------------------------------------------
    def _start(self):
        self.starts += 1
        self.mode, self.purpose = "RX", "CTRL"
        self.rises = 0
        self.shift = 0
        self.sda_slave = 1
        self.ack_out = False

    def _stop(self):
        self.stops += 1
        if self.write_start is not None and self.write_len:
            self.writes.append(
                (self.write_start,
                 bytes(self.mem[self.write_start + i] for i in range(self.write_len))))
            self.busy_until = self.clock() + WRITE_CYCLE_CYCLES
        self.write_start, self.write_len = None, 0
        self.mode = "IDLE"
        self.sda_slave = 1

    def _rise(self, sda):
        if self.mode == "RX":
            self.rises += 1
            if self.rises <= 8:
                self.shift = ((self.shift << 1) | sda) & 0xFF
        elif self.mode == "TX":
            self.rises += 1
            if self.rises == 9:
                self.master_ack = sda

    def _fall(self):
        if self.mode == "RX":
            if self.rises == 8:                       # 8 bits in: ACK the byte
                self.ack_out = self._accept_byte()
                self.sda_slave = 0 if self.ack_out else 1
                if not self.ack_out:
                    self.mode = "WAIT_STOP"
            elif self.rises == 9:                     # ACK clock done
                self.sda_slave = 1
                self.rises, self.shift = 0, 0
                if self.purpose == "TXSTART":
                    self.mode = "TX"
                    self._tx_load()
        elif self.mode == "TX":
            if self.rises < 8:
                self._tx_bit()
            elif self.rises == 8:
                self.sda_slave = 1                     # release for the master ACK
            elif self.rises == 9:
                if self.master_ack == 0:
                    self.addr = (self.addr + 1) % self.size
                    self.rises = 0
                    self._tx_load()
                else:
                    self.mode = "WAIT_STOP"
                    self.sda_slave = 1

    def _accept_byte(self):
        """Returns True to ACK the byte just received."""
        p = self.purpose
        if p == "CTRL":
            ctrl = self.shift
            if (ctrl & 0xF0) != 0xA0 or ((ctrl >> 1) & 7) != 0:
                self.mode = "WAIT_STOP"
                return False
            if self.clock() < self.busy_until:
                return False                           # still writing: NACK
            self.rw = ctrl & 1
            self.purpose = "TXSTART" if self.rw else "ADDR_H"
            return True
        if p == "ADDR_H":
            self.addr = (self.shift & 0x7F) << 8
            self.purpose = "ADDR_L"
            return True
        if p == "ADDR_L":
            self.addr |= self.shift
            self.purpose = "DATA"
            self.write_start, self.write_len = self.addr, 0
            return True
        if p == "DATA":
            base = self.addr & ~(PAGE - 1)
            a = self.write_start + self.write_len
            if (a & ~(PAGE - 1)) != base:
                self.violations.append(
                    f"write burst crosses a page boundary at ${a:04X}")
            self.mem[a % self.size] = self.shift
            self.write_len += 1
            return True
        return False

    def _tx_load(self):
        self.shift = self.mem[self.addr]
        self.rises = 0
        self._tx_bit()

    def _tx_bit(self):
        self.sda_slave = (self.shift >> (7 - self.rises)) & 1
