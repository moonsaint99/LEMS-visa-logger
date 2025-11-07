## Instruction document at the following link: [SeisLEMS TVAC User Guide](https://docs.google.com/document/d/11VcNu2kqhA4iFlFWNq3KHGkhs5XqE2UQXVg6zLiakf8/edit?usp=sharing)

VISA logger for logging Lake Shore data for SeisLEMS TVAC testing.

On the Keysight computer, at the time this is being written, the three Lake Shore devices (two 330s and the 336) are available as:

330BB: GPIB2::13::INSTR
330SP: GPIB2::12::INSTR

Device Manager shows the LS 336 on COM4, and it is accessible as:
336: ASRL4::INSTR

If the devices are unplugged and replugged, we should look out for whether their addresses change!

ASRL4::INSTR needs special configuration to interpret serial data correctly. This is listed in the 336 manual!

Baud rate: 57600
Data bits: 7
Start bits: 1
Stop bits: 1
Parity: odd
Flow control: none

Usage
- See the instructions in the google doc linked at the top of this page.
- `start-logger.bat`: launches the real-time data logger with the default settings in this repo.
- `export-logger-data.bat`: starts an interactive helper that exports samples from an existing logger SQLite database to CSV.
- `create_dummy_database.py`: creates a small SQLite database populated with synthetic samples for testing the exporter.

Configuration
- `LAKESHORE_DB`: SQLite file path. Default: `C:\\Users\\qris\\py_automations\\data_log\\lakeshore.sqlite3` for the logger. The export helper will prompt for a file but still honors this environment variable if it is set.
- `LAKESHORE_INTERVAL`: Poll interval in seconds (integer). Default: `10`
