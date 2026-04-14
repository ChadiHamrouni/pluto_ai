' Launches reminder_daemon.py silently (no console window) using pythonw.
' Add this script to Windows startup via Task Scheduler or the Startup folder.

Dim shell
Set shell = CreateObject("WScript.Shell")

' Resolve the directory this script lives in
Dim scriptDir
scriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)

' Run pythonw so no console window appears
shell.Run "pythonw """ & scriptDir & "\reminder_daemon.py""", 0, False

Set shell = Nothing
