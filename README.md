# Tome Vault

Your party's D&D library. Books live on your own Raspberry Pi or computer; everyone reads them in the Tome Vault Android app, even offline.

- **Covers as icons.** Each book's first page becomes its cover.
- **Search everything.** Find any word on any page of any book, then jump straight to it with the word highlighted.
- **Offline.** The app downloads every book to the phone and checks the vault for new or updated books each time it opens.
- **Built-in rules.** The app ships with the free System Reference Document 5.2.1, so it's useful before it ever connects.
- **Two passwords.** The *party password* lets friends read. The *keeper password* lets you add, rename, and remove books.

## Get the app

Open the [latest release](../../releases/latest) on your Android phone, tap **TomeVault.apk**, then open it to install. Android asks once to allow installs from your browser.

New versions show up as a banner inside the app. Installing one keeps your downloaded books.

## Run the vault (the server)

Needs Python 3.8 or newer, nothing else.

1. Download this repo (**Code → Download ZIP**) and unzip it.
2. Set your passwords:
   ```
   cd tome-vault/server
   python3 server.py --password YOUR_KEEPER_PASSWORD
   python3 server.py --party-password YOUR_PARTY_PASSWORD
   ```
3. Start it: `python3 server.py` (or double-click `start-windows.bat` on Windows).

The full Raspberry Pi and Tailscale Funnel setup, so friends can connect from anywhere, is in **[the setup guide](guide/Tome-Vault-Setup-Guide.pdf)**.

The vault also works in any web browser at its address.

## Optional: skip typing the address

In this repo on GitHub, go to **Settings → Secrets and variables → Actions → Variables**, add `VAULT_ADDRESS` with your vault's address (for example `https://raspberrypi.your-tailnet.ts.net`), then re-run the **Build Android app** workflow. New installs will only ask for the party password.

## How it's built

- `server/` – the vault server (Python standard library only)
- `web/` – the screens, shared by the browser version and the app
- `app/` – the Android app (Capacitor), built automatically by GitHub Actions on every push
- `scripts/` – build helpers (icon drawing, SRD preparation)

## Credits

This work includes material from the System Reference Document 5.2.1 ("SRD 5.2.1") by Wizards of the Coast LLC, available at https://www.dndbeyond.com/srd. The SRD 5.2.1 is licensed under the Creative Commons Attribution 4.0 International License, available at https://creativecommons.org/licenses/by/4.0/legalcode.

PDF rendering by [PDF.js](https://mozilla.github.io/pdf.js/) (Apache 2.0). Fonts: Cinzel and Alegreya Sans (SIL Open Font License).
