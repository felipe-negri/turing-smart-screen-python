#!/bin/bash
cd /root/turing-smart-screen-python
source myenv/bin/activate
python main.py &
echo $! > main.pid  # Salva o PID do processo pra parar depois