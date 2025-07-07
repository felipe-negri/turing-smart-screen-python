#!/bin/bash
cd /root/turing-smart-screen-python
if [ -f main.pid ]; then
    kill $(cat main.pid)
    rm main.pid
fi
