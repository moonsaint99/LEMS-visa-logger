import pyvisa

class logger:
    def __init__(self):
        self.rm = pyvisa.ResourceManager()
        self.LS330BB = self.rm.open_resource("GPIB2::13::INSTR")
        self.LS330SP = self.rm.open_resource("GPIB2::12::INSTR")

    ## Now we configure the 336 specially, because it doesn't work out of the box

        self.LS336 = self.rm.open_resource("ASRL4::INSTR")
        self.LS336.baud_rate = 57600
        self.LS336.data_bits = 7
        self.LS336.stop_bits = pyvisa.constants.StopBits.one
        self.LS336.parity = pyvisa.constants.Parity.odd
        self.LS336.flow_control = pyvisa.constants.ControlFlow.none
        self.LS336.read_termination = '\r\n'
    
    # Graceful shutdown method:
    def close(self):
        self.LS330BB.close()
        self.LS330SP.close()
        self.LS336.close()
        self.rm.close()

    def __del__(self):
        self.close()

    # Confirm connection to instruments:
    def test_instruments(self):
        try:
            self.LS330BB.query("*IDN?")
            self.LS330SP.query("*IDN?")
            self.LS336.query("*IDN?")
            print("All instruments connected successfully.")
        except Exception as e:
            print(f"Error connecting to instruments: {e}")

    ## Polling methods
    # For the 330s, we will poll setpoint and TC temperature

    def poll_330BB(self):
        try:
            setpoint = self.LS330BB.query("SETP?")
            temperature = self.LS330BB.query("TEMP?")
            return float(setpoint), float(temperature)
        except Exception as e:
            print(f"Error polling LS330BB: {e}")
            return None, None

    def poll_330SP(self):
        try:
            setpoint = self.LS330SP.query("SETP?")
            temperature = self.LS330SP.query("TEMP?")
            return float(setpoint), float(temperature)
        except Exception as e:
            print(f"Error polling LS330SP: {e}")
            return None, None

    # For the 336, we will poll setpoints and temperatures for
    # channels 1 and 2 (corresponding to A and B on the physical
    # instrument)

    def poll_336(self):
        try:
            setpoint_A = self.LS336.query("SETP? 1")
            temperature_A = self.LS336.query("TEMP? 1")
            setpoint_B = self.LS336.query("SETP? 2")
            temperature_B = self.LS336.query("TEMP? 2")
            return (float(setpoint_A), float(temperature_A)), (float(setpoint_B), float(temperature_B))
        except Exception as e:
            print(f"Error polling LS336: {e}")
            return None, None
