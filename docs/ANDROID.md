# Android build

## Easiest: build in the cloud (GitHub Actions)
1. In the repository: **Settings → Secrets and variables → Actions → New repository secret**
   * `MAZE_SUPABASE_URL` — your project URL
   * `MAZE_SUPABASE_ANON_KEY` — the **public** key (`sb_publishable_…` / anon). Never the secret key.
2. **Actions → Build Android APK → Run workflow.** The first build takes 20-40 minutes (it downloads the Android SDK/NDK);
   later ones are much faster thanks to the cache.
3. Open the finished run → **Artifacts → mazegame-debug-apk**, unzip, send the `.apk` to your phone.
4. On the phone allow *Install unknown apps* for the app you opened the file with, then install.

If the build fails, open the failed step, copy the last ~40 lines of the log and send them: first builds
of Kivy apps often need one or two small adjustments.

## Locally (Linux, needs ~10 GB and good internet)
```bash
sudo apt install -y git zip unzip openjdk-17-jdk autoconf automake libtool libltdl-dev pkg-config \
  zlib1g-dev libncurses-dev cmake libffi-dev libssl-dev build-essential
pip install buildozer "cython<3"
buildozer -v android debug      # APK appears in bin/
```
Your local `config/online.json` is bundled automatically (it only contains public values).

## Install over USB for testing
```bash
adb install -r bin/*.apk && adb logcat -s python        # see Python errors live
```

## What to test on the phone
* Drawing with your finger (all three colours), the back button (goes back one screen, closes on the menu)
* Sign in / create account with the on-screen keyboard (the field must stay visible)
* Daily challenge: play, see your rank; airplane mode: the game must keep working and say "No connection"
* Close and reopen the app: progress must still be there; uninstall/reinstall + sign in: cloud save restores it

## Before publishing on Google Play
* Change `package.domain` in `buildozer.spec` to your own: the package id can never change afterwards.
* Google raises the required *target API level* regularly: check the current requirement in the Play Console
  and update `android.api`.
* Release builds must be signed with your own keystore (`buildozer android release`, `.aab` format). Keep that
  keystore and its password safe: losing it means you can no longer update the app.
* Needed in the store listing: privacy policy, content rating, data-safety form (you store e-mail + game data).
