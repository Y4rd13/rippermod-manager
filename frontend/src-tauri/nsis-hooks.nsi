; NSIS installer hooks for RipperMod Manager.
; Kill the backend sidecar before the installer writes files,
; otherwise the .exe is locked and the install/update fails.

!macro NSIS_HOOK_PREINSTALL
  nsExec::ExecToLog 'taskkill /F /T /IM "rmm-backend.exe"'
  Pop $0
!macroend
