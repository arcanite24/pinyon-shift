# Contributing

Thanks for helping improve Pinyon Shift.

## Before opening a change

- Keep copyrighted game files, extracted assets, generated translations, build
  output, logs, dumps, and user data out of commits and issue attachments.
- Do not paste code copied or translated from the original game.
- Keep changes focused and explain how they were tested.
- Run the checks below from PowerShell on Windows.

```powershell
.\tools\check-repository-boundary.ps1
dotnet build .\launcher\PinyonShift.Launcher\PinyonShift.Launcher.csproj -c Release
python -m unittest discover -s tools\tests -p "test_*.py"
```

Changes to the runtime should also complete a local `setup-preview.ps1` build
with a supported, personally dumped disc. Never upload that build output.

## Reports

Use the issue template. Include your Windows version, CPU, GPU, driver version,
the launcher stage that failed, and the final relevant log lines. Do not attach
an ISO, XEX, extracted game files, generated `.cpp` files, or minidumps unless a
maintainer explicitly requests a private diagnostic exchange.

By contributing, you agree that your contribution is licensed under this
repository's BSD 3-Clause License.
