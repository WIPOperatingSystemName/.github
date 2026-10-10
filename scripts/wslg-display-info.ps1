# Read Windows display settings and the WSLg configuration location. No writes.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class WslgDisplay {
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct Mode {
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string DeviceName;
        public ushort SpecVersion, DriverVersion, Size, DriverExtra;
        public uint Fields;
        public int PositionX, PositionY;
        public uint DisplayOrientation, DisplayFixedOutput;
        public short Color, Duplex, YResolution, TTOption, Collate;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string FormName;
        public ushort LogPixels;
        public uint BitsPerPel, Width, Height, DisplayFlags, Frequency;
        public uint ICMMethod, ICMIntent, MediaType, DitherType;
        public uint Reserved1, Reserved2, PanningWidth, PanningHeight;
    }
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern bool EnumDisplaySettings(string device, int number, ref Mode mode);
    public static uint RefreshRate(string device) {
        Mode mode = new Mode();
        mode.Size = (ushort)Marshal.SizeOf(typeof(Mode));
        if (!EnumDisplaySettings(device, -1, ref mode))
            throw new InvalidOperationException("Cannot read active display mode: " + device);
        return mode.Frequency;
    }
}
'@

# Modern Store/MSI WSL supports --version; legacy Windows inbox WSL does not.
$null = Get-Command wsl.exe -ErrorAction Stop
try {
    # Windows PowerShell can turn native stderr into an ErrorRecord. An older
    # WSL rejecting --version is an expected probe result, not a fatal error.
    $ErrorActionPreference = 'Continue'
    $null = & wsl.exe --version 2>&1
} finally {
    $ErrorActionPreference = 'Stop'
}
if ($LASTEXITCODE -eq 0) {
    $configPath = Join-Path $env:USERPROFILE '.wslgconfig'
} else {
    $configPath = Join-Path $env:ProgramData 'Microsoft\WSL\.wslgconfig'
}
$displays = @([System.Windows.Forms.Screen]::AllScreens | ForEach-Object {
    @{
        name = $_.DeviceName
        primary = $_.Primary
        width = $_.Bounds.Width
        height = $_.Bounds.Height
        rate = [WslgDisplay]::RefreshRate($_.DeviceName)
    }
})
@{config_path = $configPath; displays = $displays} | ConvertTo-Json -Depth 3 -Compress
