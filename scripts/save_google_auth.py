
import asyncio
from playwright.async_api import async_playwright
import os

async def save_google_auth():
    async with async_playwright() as p:
        # Use real system Chrome to bypass "Not Secure" detection
        chrome_path = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
        
        browser = await p.chromium.launch(
            executable_path=chrome_path,
            headless=False
        )
        
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720}
        )
        
        page = await context.new_page()

        print("\n--- GOOGLE OAUTH LOGIN (REAL BROWSER MODE) ---")
        print("1. A browser window will open shortly.")
        print("2. Please log in with your Google account.")
        print("3. Navigate through any consent screens until you reach the app's dashboard or callback.")
        print("4. Once you have successfully logged in, come back here and I will save the session.")
        
        # Navigate to the root domain where the button is
        await page.goto("http://localhost:8000/", timeout=60000)
        
        print("\nWaiting for you to complete login... (The browser is open at the Test Portal)")
        
        # Keep the browser open until the user is done
        # We wait for the user to signal they are done or we can wait for a specific URL change
        input("\nPress ENTER here in the terminal once you have finished logging in and reached the app...")
        
        # Save storage state to a file
        storage_path = "tests/storageState.json"
        os.makedirs("tests", exist_ok=True)
        await context.storage_state(path=storage_path)
        
        print(f"\n[SUCCESS] Session saved to {storage_path}")
        print("All future tests will now run HEADLESS (no browser visible) using this session.")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(save_google_auth())
