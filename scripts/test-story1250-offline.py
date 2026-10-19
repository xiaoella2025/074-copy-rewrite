"""Run project Python acceptance with external socket connections blocked."""
import ipaddress
import faulthandler
import json
import os
from pathlib import Path
import socket
import sys
import unittest

repo=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(repo))
os.chdir(repo)
blocked=[]
original_connect=socket.socket.connect
original_connect_ex=socket.socket.connect_ex


def check_connection(sock,address):
    if sock.family not in (socket.AF_INET,socket.AF_INET6): return
    host=str(address[0]).strip('[]').lower()
    if host=='localhost':return
    try:
        if ipaddress.ip_address(host).is_loopback:return
    except ValueError:pass
    blocked.append(True)
    raise AssertionError('Offline acceptance blocked an external connection; mock this fixture transport')


def connect(sock,address):
    check_connection(sock,address);return original_connect(sock,address)


def connect_ex(sock,address):
    check_connection(sock,address);return original_connect_ex(sock,address)


def main():
    faulthandler.dump_traceback_later(120, repeat=True)
    socket.socket.connect, socket.socket.connect_ex = connect, connect_ex
    suite=unittest.defaultTestLoader.discover(str(repo/'tests'),pattern='test_*.py')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    summary={'testsRun':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
             'externalConnectionsBlocked':len(blocked),'success':result.wasSuccessful() and not blocked}
    (repo/'.desktop-tools/story1250-completion-20261019/source-python-results.json').write_text(json.dumps(summary,indent=2),'utf8')
    print(json.dumps(summary))
    raise SystemExit(not summary['success'])


if __name__=='__main__':main()
