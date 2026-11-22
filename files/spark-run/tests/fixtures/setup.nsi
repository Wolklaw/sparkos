; Spark Hello's installer, built in CI with makensis: the tiny test installer Spark Run
; installs on real Wine. Silent by itself, so it needs no display. It installs hello64.exe as
; "Spark Hello.exe", a Start Menu shortcut, and an uninstaller with its own shortcut (which
; Spark Run must not pick as the program).
Unicode true
Name "Spark Hello"
OutFile "spark-hello-setup.exe"
RequestExecutionLevel admin
SilentInstall silent
InstallDir "$PROGRAMFILES64\Spark Hello"

VIProductVersion "1.0.0.0"
VIAddVersionKey "ProductName" "Spark Hello Setup"
VIAddVersionKey "CompanyName" "Wolklaw (Spark Run test)"
VIAddVersionKey "FileDescription" "Spark Hello Setup"
VIAddVersionKey "FileVersion" "1.0.0"

Section
  SetOutPath "$INSTDIR"
  File "/oname=Spark Hello.exe" "hello64.exe"
  WriteUninstaller "$INSTDIR\uninstall.exe"
  SetShellVarContext all
  CreateDirectory "$SMPROGRAMS\Spark Hello"
  CreateShortcut "$SMPROGRAMS\Spark Hello\Spark Hello.lnk" "$INSTDIR\Spark Hello.exe"
  CreateShortcut "$SMPROGRAMS\Spark Hello\Uninstall Spark Hello.lnk" "$INSTDIR\uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$INSTDIR\Spark Hello.exe"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd
