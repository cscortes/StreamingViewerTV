# StreamingViewerTV

Your own free IPTV channel browser — no cable, no subscriptions, no accounts. Search
thousands of live channels by name, country, language, or category, and watch instantly
in your browser.

- **Thousands of free live channels**, ready to browse out of the box
- **Fast search & filters** — country, language, category, video quality, and more
- **What's on now** — live programme guide info right in the sidebar
- **Theater and fullscreen modes** for distraction-free viewing
- **Works offline** — the app ships with its own channel catalog, no account or login needed

## Download & run

No Python, no terminal, no setup — just download, unzip, and go.

Grab the latest build from the **[Releases page](../../releases/latest)**.

### Windows

1. Download `StreamingViewerTV-<version>-windows-x64.zip` and unzip it anywhere (e.g. your Desktop).
2. Open the extracted folder and double-click `StreamingViewerTV.exe`.
3. A browser tab opens automatically — you're ready to watch.

### Linux

1. Download `StreamingViewerTV-<version>-linux-x86_64.tar.gz`.
2. Extract it: `tar xzf StreamingViewerTV-*.tar.gz`
3. Run it: `./StreamingViewerTV/StreamingViewerTV`
4. A browser tab opens automatically — you're ready to watch.

The catalog bundled with each release is a snapshot as of that release's build date.
Grab a newer release from the [Releases page](../../releases) for fresher channel data.

## Using the app

- **Search** the box at the top of the sidebar to filter by channel name or metadata.
- **Filters** (category, country, language, quality, etc.) live above the channel list.
- Click any channel to start watching.
- Press **T** to toggle **Theater mode** (hides the sidebar, enlarges the player).
- Press **F** to toggle **Fullscreen**.
- The status bar at the bottom shows channel counts and playback status.

## Troubleshooting

**Windows says "Windows protected your PC" / SmartScreen warning**
The app isn't code-signed (that costs money none of this project charges for), so Windows
flags it as coming from an unrecognized publisher. Click **More info**, then **Run anyway**.

**Linux says "Permission denied" when running the app**
The extracted file lost its executable bit. Run:

```bash
chmod +x StreamingViewerTV/StreamingViewerTV
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

## Reporting problems

Found a bug, or a channel category that seems off? Please
[open an issue](../../issues/new) and include:

- What you were doing when it happened
- What you expected vs. what actually happened
- Your OS (Windows/Linux) and the app version (shown in the status bar at the bottom of the app)

## For developers

Want to build from source, contribute, or understand how the catalog is built? See
[DevReadme.md](DevReadme.md).
