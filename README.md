# StreamingViewerTV

Your own free IPTV channel browser — no cable, no subscriptions, no accounts. Search
thousands of live channels by name, country, language, or category, and watch instantly
in your browser.

- **Thousands of free live channels**, ready to browse out of the box
- **Fast search & filters**: country, language, category, video quality, and more
- **What's on now**: live programme guide info right in the sidebar, some channels only
- **Fullscreen** for distraction-free viewing (**F**)
- **Works offline**: ships with its own channel catalog, no account or login needed
- **Multiple OS Compatibility:** Windows, Linux, macOS, Android.

StreamingViewerTV — search, filters, channel list, and player

## Download & run

Grab the latest executable from the **[Releases page](../../releases/latest)**.

### Windows

1. Download `StreamingViewerTV-<version>-windows-x64.zip` and unzip it anywhere (e.g. your Desktop).
2. Open the extracted folder and double-click `StreamingViewerTV.exe`.
3. A browser tab opens automatically — you're ready to watch.



### Linux

1. Download `StreamingViewerTV-<version>-linux-x86_64.tar.gz`.
2. Extract it: `tar xzf StreamingViewerTV-*.tar.gz`
3. Run it: `./StreamingViewerTV/StreamingViewerTV`
4. A browser tab opens automatically — you're ready to watch.



### macOS (Apple Silicon)

1. Download `StreamingViewerTV-<version>-macos-arm64.tar.gz`.
2. Extract it: `tar xzf StreamingViewerTV-*.tar.gz`
3. Run it: `./StreamingViewerTV/StreamingViewerTV`
4. A browser tab opens automatically — you're ready to watch.

This build is for Apple Silicon Macs (M1/M2/M3/…). There is no prebuilt Intel Mac
archive — on an Intel Mac, build the desktop bundle from source (see
[Packaging in DevReadme.md](DevReadme.md#packaging-desktop-bundles)).

### Android (phone / tablet)

1. Download `StreamingViewerTV-<version>-android-debug.apk` from the [Releases page](../../releases).
2. On your device, allow installing apps from your browser or file manager
   (**Install unknown apps** / similar) if prompted.
3. Open the APK and install it.
4. Launch **StreamingViewerTV**. A local viewer starts on the device and opens in
   an in-app browser view — no PC required.

The Android build is a debug/sideload APK (not from the Play Store). Phones and
tablets with recent Android versions (64-bit, arm64) are supported. The UI uses
compact chrome on all platforms (see Using the app).

To rebuild the APK from source, see [android/README.md](android/README.md).

The catalog bundled with each release is a snapshot as of that release's build date.
Grab a newer release from the [Releases page](../../releases) for fresher channel data.

## Using the app

- **Search** in the slim toolbar to filter by channel name or metadata.
- **Filters** (category, country, language, quality, etc.) open from the **Filters** button (not a permanent row of dropdowns).
- On wide desktop, the channel list stays in a **docked, resizable sidebar** while browsing. On phones/tablets (narrow viewports), the list opens as an overlay drawer.
- Click any channel to start watching. The channel list stays open until you collapse it with **Hide channels** or **T**. Use **Show channels** (toolbar or the left-edge tab) or **T** again to bring the list back.
- Press **F** to toggle **Fullscreen** (also in the toolbar next to **Hide channels**).
- Star channels to save favorites (stored in this browser only). Use **Favorites** to show only starred channels.
- The status bar at the bottom shows essentials; tap **Share** for the download QR, or **Details** for the full stats.



## Troubleshooting

**Windows says "Windows protected your PC" / SmartScreen warning**
The app isn't code-signed (that costs money none of this project charges for), so Windows
flags it as coming from an unrecognized publisher. Click **More info**, then **Run anyway**.

**Linux / macOS says "Permission denied" when running the app**
The extracted file lost its executable bit. Run:

```bash
chmod +x StreamingViewerTV/StreamingViewerTV
./StreamingViewerTV/StreamingViewerTV
```

**macOS says the app "cannot be opened because the developer cannot be verified"**
The app isn't code-signed or notarized (same reason as the Windows SmartScreen
warning). In Finder, open the `StreamingViewerTV` folder, then right-click (or
Control-click) the `StreamingViewerTV` executable, choose **Open**, and confirm.
Or clear the quarantine flag from a terminal:

```bash
xattr -dr com.apple.quarantine StreamingViewerTV
./StreamingViewerTV/StreamingViewerTV
```

**No browser tab opened automatically**
Open your browser and go to [http://127.0.0.1:8787](http://127.0.0.1:8787) manually.

**"Address already in use" or the app won't start**
Another copy may already be running — check for an existing `StreamingViewerTV` process
(or browser tab at `127.0.0.1:8787`) and close it before starting a new one.

**A channel won't play**
Free public streams sometimes go offline or get geo-blocked without notice — try another
channel. If most/all channels fail to play, check your network connection.

**Antivirus flags or quarantines the app**
This can happen with any unsigned executable. The source code is fully open in this
repository if you'd like to inspect it, or you can build it yourself — see
[DevReadme.md](DevReadme.md).

**Android blocks the install (“unknown apps” / Play Protect)**
The APK isn’t from the Play Store. In the install prompt, allow your browser or
file manager to install unknown apps, or temporarily allow the install in
**Settings → Security**. If Play Protect warns, choose **Install anyway** (you can
inspect the source in this repository).

**Android app opens but no channels / blank UI**
Wait a few seconds on first launch while the local viewer starts. If it stays
blank, force-stop the app and reopen it, or reinstall a newer APK from
[Releases](../../releases).

## Reporting problems

Found a bug, or a channel category that seems off? Please
[open an issue](../../issues/new) and include:

- What you were doing when it happened
- What you expected vs. what actually happened
- Your OS (Windows/Linux/macOS/Android) and the app version (shown in the status bar at the bottom of the app)



## For developers

Want to build from source, contribute, or understand how the catalog is built? See
[DevReadme.md](DevReadme.md).