"""Explicit developer/install step. TreeTranslate never calls pip or this tool."""
import argparse
from pathlib import Path
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-network',action='store_true')
    parser.add_argument('--wheelhouse',type=Path)
    parser.add_argument('--destination',type=Path)
    args=parser.parse_args()
    if not args.allow_network and not args.wheelhouse:
        parser.error('Use --wheelhouse for offline install or explicitly --allow-network')
    root=Path(__file__).resolve().parents[1]
    destination=(args.destination or root/'.venv-ocr').resolve()
    python=destination/'Scripts/python.exe'
    if not python.exists():subprocess.run([sys.executable,'-m','venv',str(destination)],check=True)
    source=['--no-index','--find-links',str(args.wheelhouse.resolve())] if args.wheelhouse else ['--extra-index-url','https://www.paddlepaddle.org.cn/packages/stable/cu126/']
    subprocess.run([str(python),'-m','pip','install',*source,'-r',str(root/'requirements-ocr-lock.txt')],check=True)
    subprocess.run([str(python),'-m','pip','check'],check=True)


if __name__=='__main__':main()
