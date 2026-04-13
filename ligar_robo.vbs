Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "pythonw.exe tp_sync_pc.py", 0
Set WshShell = Nothing