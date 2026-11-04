from pathlib import Path
root=Path(SPECPATH).parent
# SPECPATH is packaging/; all content comes from the clean source checkout.
a=Analysis([str(root/'packaging/entry.py')],pathex=[str(root/'src')],
 datas=[(str(root/'src/workthread/web'),'workthread/web'),(str(root/'src/workthread/schemas'),'workthread/schemas'),(str(root/'workbuddy_template'),'workthread/resources/workbuddy_template')],
 hiddenimports=['keyring.backends.Windows','keyring.backends.macOS'],hookspath=[],excludes=[],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='WorkThread',console=True,upx=False)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='WorkThread')
