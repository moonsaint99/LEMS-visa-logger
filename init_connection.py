import pyvisa

class logger:
    @staticmethod
    def _safe_float(raw_value, source: str, measurement: str):
        """Best-effort conversion of VISA query responses to float.

        The Lake Shore instruments occasionally return non-numeric strings (e.g.
        "OL" for open loop).  Instead of letting ``float`` raise and breaking the
        rest of the polling cycle, coerce those responses to ``None`` and emit a
        warning so downstream logging can continue for other channels.
        """

        if raw_value is None:
            return None

        try:
            return float(raw_value)
        except (TypeError, ValueError):
            text = str(raw_value).strip()
            if text:
                print(
                    f"Warning: {source} returned non-numeric value for {measurement}: {text!r}"
                )
            else:
                print(
                    f"Warning: {source} returned empty value for {measurement}; treating as None"
                )
            return None

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
        setpoint = temperature = heater = None
        try:
            setpoint = self._safe_float(
                self.LS330BB.query("SETP?"), "LS330BB", "setpoint"
            )
        except Exception as e:
            print(f"Error polling LS330BB setpoint: {e}")

        try:
            temperature = self._safe_float(
                self.LS330BB.query("TEMP?"), "LS330BB", "temperature"
            )
        except Exception as e:
            print(f"Error polling LS330BB temperature: {e}")

        try:
            heater = self._safe_float(
                self.LS330BB.query("HEAT?"), "LS330BB", "heater"
            )
        except Exception as e:
            print(f"Error polling LS330BB heater: {e}")

        return setpoint, temperature, heater

    def poll_330SP(self):
        setpoint = temperature = heater = None
        try:
            setpoint = self._safe_float(
                self.LS330SP.query("SETP?"), "LS330SP", "setpoint"
            )
        except Exception as e:
            print(f"Error polling LS330SP setpoint: {e}")

        try:
            temperature = self._safe_float(
                self.LS330SP.query("TEMP?"), "LS330SP", "temperature"
            )
        except Exception as e:
            print(f"Error polling LS330SP temperature: {e}")

        try:
            heater = self._safe_float(
                self.LS330SP.query("HEAT?"), "LS330SP", "heater"
            )
        except Exception as e:
            print(f"Error polling LS330SP heater: {e}")

        return setpoint, temperature, heater

    # For the 336, we will poll setpoints and temperatures for
    # channels 1 and 2 (corresponding to A and B on the physical
    # instrument)

    def poll_336(self):
        a_setpoint = a_temp = b_setpoint = b_temp = None

        try:
            a_setpoint = self._safe_float(
                self.LS336.query("SETP? 1"), "LS336", "A.setpoint"
            )
        except Exception as e:
            print(f"Error polling LS336 channel A setpoint: {e}")

        try:
            a_temp = self._safe_float(
                self.LS336.query("TEMP? 1"), "LS336", "A.temperature"
            )
        except Exception as e:
            print(f"Error polling LS336 channel A temperature: {e}")

        try:
            b_setpoint = self._safe_float(
                self.LS336.query("SETP? 2"), "LS336", "B.setpoint"
            )
        except Exception as e:
            print(f"Error polling LS336 channel B setpoint: {e}")

        try:
            b_temp = self._safe_float(
                self.LS336.query("TEMP? 2"), "LS336", "B.temperature"
            )
        except Exception as e:
            print(f"Error polling LS336 channel B temperature: {e}")

        return (a_setpoint, a_temp), (b_setpoint, b_temp)

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
