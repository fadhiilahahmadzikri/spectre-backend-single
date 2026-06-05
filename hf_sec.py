from huggingface_hub import HfApi

# Initialize the API client (it will automatically use the token from huggingface-cli login)
api = HfApi()

REPO_ID = "thewhitenigs/spectre-backend"

secrets_to_upload = {
    "STATIC_API_KEY": "spk_d602c7bc949464b18c0fafc1c3c5d4f048bf2a524acad217",
    "ENCRYPTION_KEY": "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE=",
    "JWT_SECRET_KEY": "b5f00e98c9d186c353c7a0c10a1127027c0df61f2371cf1889c3",
}

print(f"Uploading secrets to {REPO_ID}...")

for key, value in secrets_to_upload.items():
    print(f" -> Setting secret: {key}")
    api.add_space_secret(repo_id=REPO_ID, key=key, value=value)

print("\nDone! Hugging Face Space will now rebuild automatically to apply the new secrets.")
