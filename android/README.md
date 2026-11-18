# DSE Report: Android app

A Kotlin shell around one hardened WebView. The card UI is bundled (`app/src/main/assets/ui/`); the report is
downloaded once a day from `https://pech-pech.github.io/dse-report/v1/latest.json`, validated, saved in the app's
private files (newest 30 sessions) and shown offline from there. One notification per new session.

| File | Does |
|---|---|
| `MainActivity.kt` | WebView through `WebViewAssetLoader` (`/assets/ui/` bundled page, `/data/` saved reports); no file/content access, no JS bridge; https links open in the browser, every other request is blocked |
| `DailyWorker.kt` | WorkManager: daily at 17:05 Dhaka (network required), retries until 21:00 on a trading day if the report is not out yet; a quiet fetch when the app opens |
| `ReportStore.kt` | checks schema 1, `asOf`, the three periods and the notification; saves atomically; NEW only for a newer session |
| `Notifier.kt` | channel "Daily report", InboxStyle; tap opens card 1, "Setups" opens card 6 |

Build (JDK 17, Android SDK 35; Gradle 8.13 comes from the wrapper):

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
./gradlew testDebugUnitTest assembleDebug        # app/build/outputs/apk/debug/app-debug.apk
node ui-test/render.test.js                      # the card UI against ui-test/fixtures/latest.json
```

The debug APK is signed with this computer's debug key: fine for side-loading, not for a store. Installing a later
build signed with a different key needs the old one uninstalled first.
