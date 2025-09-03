import pyvisa

class logger:
    def __init__(self, open_330bb: bool = True, open_330sp: bool = True, open_336: bool = True):
        self.rm = pyvisa.ResourceManager()
        if open_330bb:
            try:
                self.LS330BB = self.rm.open_resource("GPIB2::13::INSTR")
                try:
                    self.LS330BB.timeout = 1000  # ms
                except Exception:
                    pass
            except Exception as e:
                print(f"Error opening LS330BB: {e}")
        if open_330sp:
            try:
                self.LS330SP = self.rm.open_resource("GPIB2::12::INSTR")
                try:
                    self.LS330SP.timeout = 1000  # ms
                except Exception:
                    pass
            except Exception as e:
                print(f"Error opening LS330SP: {e}")

        # Now we configure the 336 specially, because it doesn't work out of the box
        if open_336:
            try:
                self.LS336 = self.rm.open_resource("ASRL4::INSTR")
                self.LS336.baud_rate = 57600
                self.LS336.data_bits = 7
                self.LS336.stop_bits = pyvisa.constants.StopBits.one
                self.LS336.parity = pyvisa.constants.Parity.odd
                self.LS336.flow_control = pyvisa.constants.ControlFlow.none
                self.LS336.read_termination = '\r\n'
                try:
                    self.LS336.timeout = 1000  # ms
                except Exception:
                    pass
            except Exception as e:
                print(f"Error opening LS336: {e}")
    
    # Graceful shutdown method:
    def close(self):
        try:
            if hasattr(self, 'LS330BB'):
                self.LS330BB.close()
        except Exception:
            pass
        try:
            if hasattr(self, 'LS330SP'):
                self.LS330SP.close()
        except Exception:
            pass
        try:
            if hasattr(self, 'LS336'):
                self.LS336.close()
        except Exception:
            pass
        try:
            self.rm.close()
        except Exception:
            pass

    def __del__(self):
        self.close()

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

    # Confirm connection to instruments:
    def test_instruments(self):
        try:
            self.LS330BB.query("*IDN?")
            self.LS330SP.query("*IDN?")
            self.LS336.query("*IDN?")
            print("All instruments connected successfully.")

            # Poll and print from each instrument:
            for i, poll_func in enumerate([self.poll_330BB, self.poll_330SP, self.poll_336]):
                result = poll_func()
                if result:
                    print(f"Instrument {i+1} - Setpoint: {result[0]}, Temperature: {result[1]}")
                else:
                    print(f"Instrument {i+1} - Failed to retrieve data.")
        except Exception as e:
            print(f"Error connecting to instruments: {e}")
