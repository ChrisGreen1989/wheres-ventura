# Where's Ventura?

A family map of the ship's position with a morning email and a fun fact. It runs free on GitHub, so your PC can stay off.

## Set it up (about 15 minutes)

1. **Get a position key.** Sign up at [aisstream.io](https://aisstream.io) and create an API key.
2. **Get a Gmail app password.** Turn on 2-Step Verification, then create one at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords). Consider using a separate Gmail account for sending.
3. **Create the repository.** Make a new **public** repository on GitHub and upload everything in this folder, including the `.github` folder. Free GitHub Pages needs a public repository.
4. **Turn on the site.** Go to **Settings > Pages** and set **Source** to **GitHub Actions**.
5. **Add the secrets.** Go to **Settings > Secrets and variables > Actions** and add:

   | Secret | Value |
   |---|---|
   | `AISSTREAM_API_KEY` | Your key from step 1 |
   | `GMAIL_ADDRESS` | The Gmail address that sends the update |
   | `GMAIL_APP_PASSWORD` | The app password from step 2 |
   | `MAIL_TO` | Who receives it. Separate several addresses with commas. If left out, it goes to the sender. |

6. **Allow the site deployment.** Go to **Settings > Environments > github-pages**. Under deployment branches, make sure `main` is allowed.
7. **Test it.** Go to **Actions > Track the ship > Run workflow**, tick **Send the email now**, and run it.

Your map is then at `https://YOUR-USERNAME.github.io/YOUR-REPOSITORY/`. Share that link with family.

## Add the ports

Edit `config.json` once you know the ports, using the schedule from your mum or the P&O booking. Add a line per stop:

```json
{ "date": "2026-11-05", "port": "Funchal, Madeira", "note": "", "lat": 32.65, "lon": -16.91 }
```

## What to expect

- The position is checked about every 30 minutes. GitHub can run scheduled jobs late, so the email at about 7:30 UTC may arrive up to an hour or so after that.
- Far from shore the signal may stop. The page and email then show the last known position and how old it is.
- Everything stops by itself after the end date in `config.json`.
- The repository and page are public, so don't add names, cabin numbers or your home address.

## Check the code

```bash
pip install -r requirements.txt
python tests/test_tracker.py
```
