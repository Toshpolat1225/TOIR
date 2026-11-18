# Generates the test recordings with the Windows Russian voice (System.Speech). Uzbek has no installed voice: see README in speech_measure.py.
# Run:  powershell -ExecutionPolicy Bypass -File generate_samples.ps1
Add-Type -AssemblyName System.Speech
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$phrases = Get-Content -Raw -Encoding UTF8 (Join-Path $dir "phrases.json") | ConvertFrom-Json
$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice.SelectVoice("Microsoft Irina Desktop")
$voice.Rate = 0
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
foreach ($p in $phrases) {
    $path = Join-Path $dir ($p.id + ".wav")
    $voice.SetOutputToWaveFile($path, $format)
    $voice.Speak($p.say)
    $voice.SetOutputToNull()
    "{0} -> {1} KB" -f $p.id, [math]::Round((Get-Item $path).Length / 1KB)
}
