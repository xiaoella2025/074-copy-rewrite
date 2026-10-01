' app074 启动器（无窗口）
' 已经有一个 074 在跑时不再启 pythonw，直接开浏览器
Dim sa, shell, fso
Set sa    = CreateObject("Shell.Application")
Set shell = CreateObject("WScript.Shell")
Set fso   = CreateObject("Scripting.FileSystemObject")

Dim py, appdir, url
py     = "C:\Users\Admin\AppData\Local\Programs\Python\Python314\pythonw.exe"
appdir = "D:\1Leida-shipinhao\074-copy-rewrite"
url    = "http://127.0.0.1:18801"

' 1. 探测 18801 是否已在监听
Dim alreadyRunning
alreadyRunning = False
On Error Resume Next
Dim http
Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
http.SetTimeouts 300, 300, 300, 300
http.Open "GET", url & "/api/settings", False
http.Send
If Err.Number = 0 Then
    If http.Status = 200 Then alreadyRunning = True
End If
On Error Goto 0

' 2. 没在跑才启动
If Not alreadyRunning Then
    sa.ShellExecute py, """" & appdir & "\server.py""", appdir, "open", 0
    WScript.Sleep 3000
End If

' 3. 找浏览器
Dim edge
edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

If fso.FileExists(edge) Then
    sa.ShellExecute edge, "--new-window " & url, "", "open", 1
Else
    shell.Run url, 1, False
End If