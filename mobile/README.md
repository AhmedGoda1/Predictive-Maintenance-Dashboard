# PdM Technician: Android test app

A Capacitor wrapper for the XIOS3 predictive maintenance app. The Android app has one full-screen
WebView that opens the deployed CloudBackend site, so every redeploy shows up in the app without a
rebuild. It is for testing on your own phone, not for a store release.

Versions: Capacitor 8.6.0 (needs Node.js 22 or newer), Android 7.0+ (minSdk 24), built with the JDK 21
that ships with Android Studio.

## One-time setup

1. Install **Android Studio** (developer.android.com/studio), open it once and accept the "Standard" setup
   so it downloads the Android SDK.
2. Check Node: `node -v` in PowerShell must print v22 or newer. If not, install the LTS from nodejs.org.
3. The app address is already set in `capacitor.config.json` (`server.url`,
   https://jodu-joduowner-pdmtechnician.cloudbackend.cloud/). Change it there if the deployment moves.

## Build and run

In PowerShell, in this folder:

```
npm install
npx cap add android
npx cap open android
```

Android Studio opens the `android` project. Let Gradle finish syncing (bottom status bar), then:

- **On your phone:** enable Developer options (Settings > About phone > tap Build number 7 times), turn on
  USB debugging, plug in the phone, pick it in the device list at the top and press Run (green triangle).
- **Or on an emulator:** Device Manager > Create device (for example Pixel 8), then Run.

After changing `capacitor.config.json`, run `npx cap sync android` and press Run again.
Changes to the XIOS3 app itself need no rebuild: redeploy, then close and reopen the app.

## What to test

- Sign in, close the app fully, reopen: are you still signed in? (Expected no, until `<login session="true">`
  is accepted by CloudBackend; this is the main thing the wrapper can tell us.)
- The phone layout: list first, detail after a tap, Back, the work-order buttons.
- The Android back button (it currently goes back in the WebView's history or closes the app).

## Debugging

With the app running, open `chrome://inspect` in Chrome on the PC: the app's WebView is listed there and
"inspect" gives the same console as in the browser.
