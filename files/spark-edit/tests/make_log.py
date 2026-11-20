"""Write a log file of about N megabytes, like a system journal export: the file the README's
open time is measured with.  python3 make_log.py OUT.log 50"""

import random
import sys


def main(path: str, megabytes: float) -> None:
    rng = random.Random(1)
    words = ("kernel usb device connected audio pipewire session started stopped error "
             "warning info debug network wlan0 eth0 link up down mounted /dev/nvme0n1p3 "
             "temperature fan steam gamescope proton").split()
    target = int(megabytes * 1024 * 1024)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        i = 0
        while f.tell() < target:
            i += 1
            f.write(f"2026-11-20T03:{i // 3600 % 60:02d}:{i // 60 % 60:02d}.{i % 1000:03d} "
                    f"sparkos {rng.choice(words)}[{rng.randint(100, 99999)}]: "
                    + ' '.join(rng.choice(words) for _ in range(rng.randint(4, 14))) + '\n')


if __name__ == '__main__':
    main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 50)
