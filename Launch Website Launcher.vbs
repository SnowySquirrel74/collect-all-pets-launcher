Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = shell.ExpandEnvironmentStrings("%USERPROFILE%") & "\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
script = appDir & "\website_launcher.py"

If Not fso.FileExists(pythonw) Then
    pythonw = "pythonw"
End If

shell.CurrentDirectory = appDir
shell.Run """" & pythonw & """ """ & script & """", 0, False
