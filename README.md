VISA logger for logging Lake Shore data for SeisLEMS TVAC testing

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