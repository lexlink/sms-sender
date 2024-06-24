import sys
import os
from pathlib import Path
from multiprocessing import Process
import subprocess

LOG_FILE = 'uvicorn.log'
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10 MB

def run_telegrambot():
    sys.path.append(str(Path(__file__).resolve().parent))
    import telegrambot
    telegrambot.main()

def run_main():
    log_file = Path(LOG_FILE)

    while True:
        # Check the log file size
        if log_file.exists() and log_file.stat().st_size >= MAX_LOG_SIZE:
            # Truncate the log file if it exceeds the maximum size
            with log_file.open('w') as f:
                f.truncate(0)

        # Open a file for the log output from the subprocess
        with log_file.open('a') as f:
            # Redirect the output and error streams of the subprocess to the file
            subprocess.run(['uvicorn', 'main:app', '--host', '0.0.0.0', '--log-level', 'debug'], stdout=f, stderr=f)

def main():
    try:
        telegrambot_process = Process(target=run_telegrambot)
        main_process = Process(target=run_main)

        telegrambot_process.start()
        main_process.start()

        telegrambot_process.join()
        main_process.join()
    except KeyboardInterrupt:
        # Terminate the processes on keyboard interrupt
        telegrambot_process.terminate()
        main_process.terminate()

if __name__ == '__main__':
    main()
