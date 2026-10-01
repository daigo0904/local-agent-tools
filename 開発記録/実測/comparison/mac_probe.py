#!/usr/bin/env python3
"""Witness-only macOS A/C probes, fresh temporary directories and explicit outcomes."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from preflight import witness

CASES = {
    'forge': "p.write_text('FORGED\\n')",
    'erase': 'p.unlink()',
    'truncate': "p.write_text('')",
    'fifo': 'p.unlink(); os.mkfifo(p)',
    'kill': 'os.kill(os.getppid(),9)',
    'write': "Path('out').write_text('ok')",
    'temporary': "Path(os.environ['TMPDIR'],'out').write_text('ok')",
    'child_signal': "import subprocess; c=subprocess.Popen([sys.executable,'-c','import time;time.sleep(0.5)']); c.terminate(); assert c.wait(timeout=2)==-15; Path('out').write_text('ok')",
    'self_signal': "os.kill(os.getpid(),0); Path('out').write_text('ok')",
}

def main():
    rows=[]
    for name, operation in CASES.items():
        for arm, source in zip(('control','candidate'), sys.argv[1:]):
            with tempfile.TemporaryDirectory() as td:
                root=Path(td).resolve(); work=root/'work'; work.mkdir()
                evidence=root/'evidence'; evidence.mkdir(); record=evidence/'見届け.txt'
                script=root/'witness.py'
                script.write_text(witness(Path(source)).replace('__上限__','None').replace('__書ける__',repr([str(work)])))
                code="from pathlib import Path; import os,sys; p=Path(sys.argv[1]); "+operation
                import os
                result=subprocess.run([sys.executable,str(script),str(record),sys.executable,'-c',code,str(record)],
                    cwd=work,env=dict(os.environ,TMPDIR=str(evidence)),capture_output=True,text=True,timeout=10)
                import stat
                regular=record.exists() and stat.S_ISREG(record.lstat().st_mode)
                content=record.read_text() if regular else None
                if name in ('write','temporary','child_signal','self_signal'):
                    out=(work/'out') if name!='temporary' else evidence/('中/out' if arm=='candidate' else 'out')
                    ok=result.returncode==0 and out.read_text()=='ok'
                elif arm=='candidate':
                    ok=result.returncode==1 and regular and content.startswith('起動\n閉じ込め seatbelt') and 'PermissionError' in result.stderr
                else:
                    ok=result.returncode==(-9 if name=='kill' else 0)
                row=dict(case=name,arm=arm,exit_code=result.returncode,record=content,stderr=result.stderr,passed=ok)
                rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
    print(json.dumps({'complete':len(rows),'passed':sum(r['passed'] for r in rows)}))
    return all(r['passed'] for r in rows)

if __name__=='__main__':
    raise SystemExit(0 if main() else 1)
