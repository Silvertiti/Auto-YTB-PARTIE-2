import subprocess
import os
import glob

# Ensure we run in /app
os.chdir("/app")

input_path = "youtube_crashes_output/temp_clips/SnappyBitterButterflyTBTacoRight-zwwdJuXFnk9Gl2wa_raw.mp4"
output_path = "youtube_crashes_output/processed_chunks/test_std.mp4"
streamer_name = "Gotaga"
FONT_PATH = "Nunito-Black.ttf"

# Check if file exists
if not os.path.exists(input_path):
    files = glob.glob("youtube_crashes_output/temp_clips/*.mp4")
    if files:
        input_path = files[0]
        
print("Input path:", input_path)
if not os.path.exists(input_path):
    print("❌ No input clip found to test!")
    exit(1)

dur = 5.0
abs_font_path = os.path.abspath(FONT_PATH).replace("\\", "/").replace(":", "\\:")
safe_name = streamer_name.replace(":", "").replace("'", "")

filter_complex = (
    f"[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,"
    f"scale='1920*(1+0.03*t/{dur})':'1080*(1+0.03*t/{dur})':eval=frame,crop=1920:1080:(iw-1920)/2:(ih-1080)/2[pre_text]"
)
vf_input_label = "[pre_text]"

drawtext_filter = (
    f"drawtext=fontfile='{abs_font_path}':text='{safe_name}':"
    f"fontcolor=white:fontsize=48:x=60:y=60:"
    f"shadowcolor=black:shadowx=3:shadowy=3"
)

fade_filters = f"fade=in:st=0:d=0.3,fade=out:st={dur-0.3:.3f}:d=0.3"
full_vf = f"{filter_complex};{vf_input_label}{drawtext_filter},{fade_filters}[out_v]"

af_chain = f"dynaudnorm=f=150:g=15,afade=in:st=0:d=0.3,afade=out:st={dur-0.3:.3f}:d=0.3"
full_af = f"[0:a]{af_chain}[out_a]"

cmd = [
    "ffmpeg", "-y", "-ss", "0.5", "-t", "4.0",
    "-i", input_path,
    "-filter_complex", f"{full_vf};{full_af}",
    "-map", "[out_v]", "-map", "[out_a]",
    "-c:v", "libx264", "-preset", "fast", "-r", "60",
    "-c:a", "aac", "-ar", "44100", "-b:a", "192k",
    "-y", output_path
]

print("Running command:", " ".join(cmd))
res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
print("Return code:", res.returncode)
print("STDOUT length:", len(res.stdout))
print("STDERR:")
print(res.stderr)
