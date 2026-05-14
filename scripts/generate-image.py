#!/usr/bin/env python3
"""
A+ Tutoring DALL-E 3 image generation utility.
Generates branded education imagery from prompts.
"""
import os
import sys
import argparse
import requests
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
BUDGET = float(os.getenv("DALL_E_MONTHLY_BUDGET", "50.00"))
LOG_PATH = Path(__file__).parent / "dall-e-usage.log"

COSTS = {
    ("1024x1024", "standard"): 0.040,
    ("1024x1024", "hd"): 0.080,
    ("1792x1024", "standard"): 0.080,
    ("1792x1024", "hd"): 0.120,
    ("1024x1792", "standard"): 0.080,
    ("1024x1792", "hd"): 0.120,
}

def get_monthly_spend():
    if not LOG_PATH.exists():
        return 0.0
    current_month = datetime.now().strftime("%Y-%m")
    spend = 0.0
    with open(LOG_PATH) as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry["timestamp"].startswith(current_month):
                    spend += entry["cost"]
            except (json.JSONDecodeError, KeyError):
                continue
    return spend

def log_usage(prompt, size, quality, cost, output_path, success):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "prompt_preview": prompt[:100],
        "size": size,
        "quality": quality,
        "cost": cost,
        "output_path": str(output_path),
        "success": success,
    }
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")

def generate(prompt, output_path, size="1792x1024", quality="standard", style="natural"):
    if not API_KEY or API_KEY == "PLACEHOLDER_REPLACE_WITH_REAL_KEY":
        print("ERROR: OPENAI_API_KEY not set in .env", file=sys.stderr)
        return 1

    cost = COSTS.get((size, quality), 0.08)
    monthly_spend = get_monthly_spend()

    if monthly_spend + cost > BUDGET:
        print(f"ERROR: Generation would exceed monthly budget. Current: ${monthly_spend:.2f}, Budget: ${BUDGET:.2f}", file=sys.stderr)
        return 1

    print(f"Generating image. Cost estimate: ${cost:.3f}. Monthly spend so far: ${monthly_spend:.2f}/${BUDGET:.2f}")

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "dall-e-3",
        "prompt": prompt,
        "n": 1,
        "size": size,
        "quality": quality,
        "style": style,
        "response_format": "url",
    }

    try:
        response = requests.post(
            "https://api.openai.com/v1/images/generations",
            headers=headers,
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        image_url = data["data"][0]["url"]

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        img_response = requests.get(image_url, timeout=60)
        img_response.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(img_response.content)

        log_usage(prompt, size, quality, cost, output_path, True)
        print(f"Image saved to: {output_path}")
        return 0

    except requests.exceptions.RequestException as e:
        print(f"ERROR: API request failed: {e}", file=sys.stderr)
        log_usage(prompt, size, quality, 0, output_path, False)
        return 1
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        log_usage(prompt, size, quality, 0, output_path, False)
        return 1

def main():
    parser = argparse.ArgumentParser(description="Generate images via DALL-E 3 for A+ Tutoring")
    parser.add_argument("--prompt", required=True, help="DALL-E 3 prompt")
    parser.add_argument("--output", required=True, help="Output file path (PNG)")
    parser.add_argument("--size", default="1792x1024", choices=["1024x1024", "1792x1024", "1024x1792"])
    parser.add_argument("--quality", default="standard", choices=["standard", "hd"])
    parser.add_argument("--style", default="natural", choices=["natural", "vivid"])
    args = parser.parse_args()

    return generate(args.prompt, args.output, args.size, args.quality, args.style)

if __name__ == "__main__":
    sys.exit(main())
