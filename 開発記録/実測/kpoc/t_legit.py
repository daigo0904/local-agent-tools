import sys, os, tempfile; sys.path.insert(0,'/k'); import landlock_mitodoke as L
版=L.abi(); 根=tempfile.mkdtemp(); w=os.path.join(根,'w'); os.mkdir(w); e=os.path.join(根,'e')
中="import os\nopen('a.txt','w').write('x'); os.mkdir('d'); open('d/b','w').write('y'); os.rename('a.txt','c.txt'); os.unlink('d/b'); print(sorted(os.listdir('.')))"
code,_=L.見届けて走らせる([sys.executable,'-c',中], w, e, True, 版)
print('終了',code,'作業場',sorted(os.listdir(w)),'証拠',open(e).read().split())
