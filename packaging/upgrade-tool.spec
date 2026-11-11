from pathlib import Path
root=Path(SPECPATH).parent
key=root/'packaging/release-public.hex'
a=Analysis([str(root/'standalone/entry.py')],pathex=[str(root/'src')],
 datas=[(str(key),'workthread/updating'),(str(root/'src/workthread/web'),'workthread/web'),(str(root/'src/workthread/schemas'),'workthread/schemas'),(str(root/'workbuddy_template'),'workthread/resources/workbuddy_template')],
 hiddenimports=['keyring.backends.Windows'],hookspath=[],excludes=[],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='WorkThreadUpgrade',console=True,upx=False)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='WorkThreadUpgrade')
