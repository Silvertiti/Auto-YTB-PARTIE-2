import requests

prompt = (
    "hand-drawn and flat-colored bust portrait illustration, "
    "in the exact minimalist and unrefined graphic style of wankul studio french youtubers, "
    "the subject is a stylized humanoid robot character, "
    "with a slightly disproportionate and bulbous head shape, "
    "neutral blank facial expression, dot eyes and simple line mouth, "
    "spiky mechanical hairstyle with a bolt detail instead of a hair strand, "
    "wearing a sage green t-shirt with graphic text print: "
    "black vertical bar with text CPU, red vertical bar with text RAM, "
    "plain clean white background, "
    "thick freehand black outlines, flat basic coloring, no shading, no texture, "
    "partial profile angle view, "
    "franco-belgian bande dessinee ligne claire style, "
    "2D flat illustration, comic book art"
)

neg = (
    "3d, realistic, anime, chibi, manga, shading, gradients, shadows, "
    "detailed texture, photorealistic, blurry, watermark, nsfw"
)

encoded = requests.utils.quote(prompt)
url = "https://image.pollinations.ai/prompt/" + encoded
params = {
    "model": "flux",
    "width": 768,
    "height": 768,
    "nologo": "true",
    "seed": "42",
    "enhance": "false",
}

print("Generation en cours...")
resp = requests.get(url, params=params, timeout=180)
ct = resp.headers.get("Content-Type", "")
print(f"Status: {resp.status_code}  Type: {ct}")

if resp.status_code == 200 and "image" in ct:
    with open("wankul_robot.png", "wb") as f:
        f.write(resp.content)
    print("OK -> wankul_robot.png")
else:
    print("FAIL:", resp.text[:300])
