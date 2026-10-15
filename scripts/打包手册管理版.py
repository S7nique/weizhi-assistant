"""构建独立的手册管理版，不覆盖已有运行包。"""
from pathlib import Path
import os,subprocess
ROOT=Path(__file__).resolve().parents[1]
args=[str(ROOT/'.venv/Scripts/python.exe'),'-m','PyInstaller','--noconfirm','--onedir','--windowed','--name','维知助手',
      '--distpath',str(ROOT.parent/'交付/手册管理版'),'--workpath',str(ROOT/'构建缓存_手册'),
      '--specpath',str(ROOT/'核验/手册构建'),'--add-data',str(ROOT/'src')+';resources/src',
      '--add-data',str(ROOT/'tests/fixtures')+';resources/fixtures',
      '--collect-all','webview',str(ROOT/'desktop.py')]
with (ROOT/'核验/手册版打包日志.txt').open('w',encoding='utf-8') as output:
    result=subprocess.run(args,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,env=dict(os.environ,PYTHONUTF8='1'))
if result.returncode:raise SystemExit('打包失败，请查看核验/手册版打包日志.txt')
print('MANUAL_DESKTOP_BUILD PASS')
